"""大模型接入的测试。

全部用 `httpx.MockTransport` 打桩，**不需要真实密钥、不发起任何网络请求**。
覆盖 spec `ai-enhancement` 里要求的全部降级路径，以及「AI 不许编造事实」
这条硬要求的具体防线。
"""

from __future__ import annotations

import json

import httpx
import pytest

from src import ai_enhance, ai_service, config
from src.ai_service import AIService, extract_json_object, redact
from src.data_loader import Product
from src.demand_parser import Demand
from src.errors import (
    AINotConfigured,
    UpstreamAuthError,
    UpstreamResponseError,
    UpstreamTimeout,
    UpstreamUnavailable,
    ZhigouError,
)

FAKE_KEY = "sk-test-not-a-real-key-000000"


def make_service(handler, **kwargs) -> AIService:
    """构造一个走打桩传输的服务。"""
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    options = {
        "api_key": FAKE_KEY,
        "base_url": "https://example.invalid/v1",
        "model": "test-model",
        "timeout_s": 5,
        "max_tokens": 512,
        "client": client,
    }
    options.update(kwargs)
    return AIService(**options)


def ok_body(content: str = "你好", **extra) -> dict:
    message = {"role": "assistant", "content": content}
    message.update(extra.pop("message", {}))
    body = {
        "model": "test-model",
        "choices": [{"message": message, "finish_reason": extra.pop("finish_reason", "stop")}],
        "usage": {"total_tokens": 42, "completion_tokens_details": {"reasoning_tokens": 7}},
    }
    body.update(extra)
    return body


# --------------------------------------------------------------------------
# 未配置
# --------------------------------------------------------------------------


def test_unconfigured_service_reports_it():
    assert AIService(api_key="").configured is False


def test_unconfigured_service_raises_before_any_request():
    """spec：密钥未配置时在**发请求之前**就报错。"""
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=ok_body())

    service = make_service(handler, api_key="")
    with pytest.raises(AINotConfigured) as excinfo:
        service.complete("system", "user")

    assert calls == [], "没配密钥却发出了请求"
    assert config.LLM_API_KEY_ENV in excinfo.value.user_message


def test_describe_never_leaks_the_key():
    service = make_service(lambda r: httpx.Response(200, json=ok_body()))
    described = service.describe()

    assert FAKE_KEY not in json.dumps(described, ensure_ascii=False)
    assert described["configured"] is True


# --------------------------------------------------------------------------
# 降级路径
# --------------------------------------------------------------------------


def test_timeout_becomes_a_domain_error():
    def handler(request):
        raise httpx.ReadTimeout("too slow", request=request)

    with pytest.raises(UpstreamTimeout) as excinfo:
        make_service(handler).complete("s", "u")
    assert "本地规则模式" in excinfo.value.user_message


def test_connection_failure_becomes_unavailable():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(UpstreamUnavailable):
        make_service(handler).complete("s", "u")


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_is_named_clearly(status):
    def handler(request):
        return httpx.Response(status, json={"error": "invalid key"})

    with pytest.raises(UpstreamAuthError) as excinfo:
        make_service(handler).complete("s", "u")
    assert "密钥" in excinfo.value.user_message


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_rate_limit_and_server_errors_degrade(status):
    def handler(request):
        return httpx.Response(status, text="upstream boom")

    with pytest.raises(UpstreamUnavailable):
        make_service(handler).complete("s", "u")


def test_non_json_response_body_is_rejected():
    def handler(request):
        return httpx.Response(200, text="<html>not json</html>")

    with pytest.raises(UpstreamResponseError):
        make_service(handler).complete("s", "u")


def test_unexpected_structure_is_rejected():
    def handler(request):
        return httpx.Response(200, json={"choices": []})

    with pytest.raises(UpstreamResponseError):
        make_service(handler).complete("s", "u")


def test_empty_content_is_rejected_not_treated_as_an_answer():
    def handler(request):
        return httpx.Response(200, json=ok_body(content=""))

    with pytest.raises(UpstreamResponseError):
        make_service(handler).complete("s", "u")


def test_truncated_empty_content_explains_the_token_limit():
    """推理模型把额度吃光的典型表现。

    这不是「模型没话说」，而是 token 不够——当成成功返回空串会让上层
    误以为「AI 认为没有可提取的信息」，所以必须报错并给出可操作的提示。
    """
    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content="",
                finish_reason="length",
                usage={
                    "total_tokens": 512,
                    "completion_tokens_details": {"reasoning_tokens": 512},
                },
            ),
        )

    with pytest.raises(UpstreamResponseError) as excinfo:
        make_service(handler).complete("s", "u")

    assert "token" in excinfo.value.user_message.lower() or "额度" in excinfo.value.user_message


def test_error_body_never_leaks_the_key_into_the_message():
    """4xx 的响应体可能回显请求头，异常信息必须脱敏。"""
    def handler(request):
        return httpx.Response(400, text=f"bad request with Authorization: Bearer {FAKE_KEY}")

    with pytest.raises(UpstreamUnavailable) as excinfo:
        make_service(handler).complete("s", "u")

    assert FAKE_KEY not in (excinfo.value.detail or "")
    assert FAKE_KEY not in excinfo.value.user_message


# --------------------------------------------------------------------------
# 正常路径
# --------------------------------------------------------------------------


def test_successful_call_returns_content_and_usage():
    def handler(request):
        return httpx.Response(200, json=ok_body(content="可用"))

    result = make_service(handler).complete("system", "user")

    assert result.content == "可用"
    assert result.model == "test-model"
    assert result.total_tokens == 42
    assert result.reasoning_tokens == 7
    assert result.truncated is False


def test_request_uses_openai_compatible_shape():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body())

    make_service(handler).complete("系统提示", "用户输入", max_tokens=128)

    assert captured["url"].endswith("/chat/completions")
    assert captured["auth"] == f"Bearer {FAKE_KEY}"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["max_tokens"] == 128
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["stream"] is False


def test_reasoning_content_is_not_surfaced():
    """推理过程不给用户看：可能是英文、可能复述提示词。"""
    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content="答案",
                message={"reasoning_content": "Let me think about the prompt..."},
            ),
        )

    result = make_service(handler).complete("s", "u")

    assert result.content == "答案"
    assert not hasattr(result, "reasoning_content")
    assert "reasoning_content" not in json.dumps(result.__dict__)


def test_endpoint_is_replaceable_without_code_changes():
    """spec：换环境变量即可切换端点与模型，不用改业务代码。"""
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, json=ok_body())

    service = make_service(handler, base_url="https://other.example.com/v2/", model="别的模型")
    service.complete("s", "u")

    assert seen["url"].startswith("https://other.example.com/v2/")
    assert seen["model"] == "别的模型"


# --------------------------------------------------------------------------
# 密钥脱敏
# --------------------------------------------------------------------------


def test_redact_removes_the_configured_key():
    assert FAKE_KEY not in redact(f"请求失败，Authorization: Bearer {FAKE_KEY}")


def test_redact_catches_any_key_shaped_string():
    """换个 key 但忘了更新环境变量时，也不能漏出去。"""
    other = "sk-abcdef1234567890abcdef"
    assert other not in redact(f"leaked {other} here")


def test_redact_leaves_normal_text_alone():
    text = "商品 LP001 的参考价是 3299 元，评分 43 分。"
    assert redact(text) == text


# --------------------------------------------------------------------------
# JSON 提取
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        '好的，这是结果：{"a": 1} 以上。',
    ],
)
def test_extract_json_handles_common_wrappers(raw):
    assert extract_json_object(raw) == {"a": 1}


@pytest.mark.parametrize("raw", ["随便说点什么", "", "[1, 2, 3]", "{不是合法 json"])
def test_extract_json_returns_none_when_hopeless(raw):
    assert extract_json_object(raw) is None


def test_complete_json_raises_when_the_model_will_not_cooperate():
    def handler(request):
        return httpx.Response(200, json=ok_body(content="我不确定，你看着办吧"))

    with pytest.raises(UpstreamResponseError):
        make_service(handler).complete_json("s", "u")


# --------------------------------------------------------------------------
# 需求解析：模型输出一律当不可信输入
# --------------------------------------------------------------------------


def test_payload_outside_allowed_values_is_dropped(monkeypatch):
    payload = {
        "category": "tablet",              # 不在枚举里
        "budget": -100,                    # 负数
        "use_cases": ["编程", "写代码", "旅游"],  # 最后一个不在词表里
        "core_needs": ["性能", "玄学"],     # 最后一个不在词表里
        "compromises": [" 可以重一点 ", ""],
        "brand_preferences": ["轻羽"],
        "hard_constraints": ["降噪", "必须有钱"],  # 最后一个不在表里
    }

    demand = ai_enhance.demand_from_payload(payload, "原始输入")

    assert demand.category == ""
    assert demand.budget is None
    assert demand.use_cases == ["编程"]
    assert demand.core_needs == ["性能"]
    assert demand.compromises == ["可以重一点"]
    assert demand.hard_constraints == ["降噪"]
    assert demand.source == "ai"
    assert demand.raw_text == "原始输入"


def test_payload_with_wrong_types_does_not_crash():
    payload = {
        "category": 123,
        "budget": "三千",
        "use_cases": "编程",
        "core_needs": None,
        "compromises": {"a": 1},
        "brand_preferences": 42,
        "hard_constraints": "降噪",
    }

    demand = ai_enhance.demand_from_payload(payload, "x")

    assert demand.category == ""
    assert demand.budget is None
    assert demand.use_cases == []
    assert demand.brand_preferences == []
    assert demand.hard_constraints == []


def test_numeric_string_budget_is_accepted():
    demand = ai_enhance.demand_from_payload({"budget": "3500"}, "x")
    assert demand.budget == 3500


def test_parse_with_ai_goes_through_the_service():
    captured = {}

    def handler(request):
        body = json.loads(request.content)
        captured["user"] = body["messages"][1]["content"]
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {"category": "laptop", "budget": 3000, "use_cases": ["编程"],
                     "core_needs": ["性能"], "compromises": [],
                     "brand_preferences": [], "hard_constraints": []},
                    ensure_ascii=False,
                )
            ),
        )

    demand = ai_enhance.parse_demand_with_ai(
        "预算 3000 买笔记本写代码", service=make_service(handler), known_brands=["轻羽", "墨砚"]
    )

    assert demand.category == "laptop"
    assert demand.budget == 3000
    assert "轻羽" in captured["user"], "已知品牌应作为提示传进去"


# --------------------------------------------------------------------------
# 编造事实的防线
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, allowed, expected",
    [
        ("参考价 3299 元，性价比不错", {3299.0}, []),
        ("价格 ¥3,299 元", {3299.0}, []),
        ("参考价 2599 元，性价比不错", {3299.0}, [2599.0]),
        ("价格 3,299 元", {}, [3299.0]),      # 千分位要正确解析，不能被逗号切断
        ("续航 10 小时，整机 1.28kg", {3299.0}, []),
    ],
)
def test_find_invented_prices(text, allowed, expected):
    assert ai_enhance.find_invented_prices(text, allowed) == expected


def test_explanation_with_a_wrong_price_is_dropped(catalog):
    """模型顺口说一个数据里没有的价格——这条解读必须被丢掉。"""
    real_price = catalog.get("LP001").price

    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {
                        "overview": "总结",
                        "per_product": [
                            {"product_id": "LP001", "why": f"只要 {real_price:.0f} 元，很划算"},
                            {"product_id": "LP002", "why": "只要 1234 元，非常便宜"},
                        ],
                    },
                    ensure_ascii=False,
                )
            ),
        )

    items = [_item(catalog.get("LP001")), _item(catalog.get("LP002"))]
    result = ai_enhance.explain_recommendations(
        Demand(category="laptop", budget=8000), items, service=make_service(handler)
    )

    per_product = result["per_product"]
    assert "LP001" in per_product
    assert "LP002" not in per_product, "价格对不上的解读没有被丢掉"
    assert "LP002" in result["dropped"]


# 数值断言的基准从数据里现取（见 `_real_specs`），不写死具体数字。


def test_real_spec_values_are_accepted(catalog):
    """与数据一致的数值必须放过——校验过严会把好解读一起杀掉。

    这是当初价格校验踩过的坑，参数校验同样要防。
    """
    real = _real_specs(catalog)
    allowed = ai_enhance.spec_claim_values([catalog.get("LP001")])

    for text in (
        f"续航约 {real['battery']:.0f} 小时，通勤够用",
        f"整机 {real['weight']} 千克，背一天不累",
        f"{real['ram']:.0f}GB 内存够跑开发环境",
        f"{real['screen']:.0f} 英寸屏幕，放包里刚好",
        # 四舍五入不算编造——真实值本身就是「约」的表达
        f"重量约 {real['weight']:.1f} 千克",
        # 参数族里压根没有数据时不判定——缺数据不等于编造
        "电池 5000mAh",
        # 裸数字不该被当成参数断言（序号、评分、年份）
        "在候选里排第 1，得分 88 分，2026 年的数据",
    ):
        assert ai_enhance.find_unsupported_spec_claims(text, allowed) == [], text


def test_invented_spec_values_are_caught(catalog):
    """数据里没有的数值必须抓住。

    编造值由真实值推出来（翻倍、减半），这样无论数据集换成什么，
    它们都**保证**不在允许集合里——写死一个「20 小时」，哪天数据里
    真出现 20 小时续航的机器，这条测试就会开始放过真正的编造。
    """
    real = _real_specs(catalog)
    allowed = ai_enhance.spec_claim_values([catalog.get("LP001")])

    cases = [
        (f"续航长达 {real['battery'] * 2:.0f} 小时", [f"{real['battery'] * 2:.0f} 小时"]),
        (f"重量只有 {real['weight'] / 2:.1f} 千克", [f"{real['weight'] / 2:.1f} 千克"]),
        (f"{real['ram'] * 2:.0f}GB 内存够用", [f"{real['ram'] * 2:.0f}GB"]),
    ]
    for text, expected in cases:
        assert ai_enhance.find_unsupported_spec_claims(text, allowed) == expected, text


def test_integer_claims_get_no_rounding_allowance(catalog):
    """取整半径只给带小数的断言，整数断言一点不给。

    这条钉住容差设计里刻意排除的那个方案：若按写法精度给整数断言取半径，
    「1TB」就变成区间 [0.5, 1.5] TB，半径足以吞掉数据里的 512GB——
    等于放过了量级级的高报，而高报恰恰是幻觉里最危险的一种。
    """
    product = catalog.get("LP001")
    allowed = ai_enhance.spec_claim_values([product])
    storage = float(product.spec("storage_gb"))

    exact = f"{storage:.0f}GB"
    assert ai_enhance.find_unsupported_spec_claims(f"{exact} 固态", allowed) == []

    halved = f"{storage / 2:.0f}GB"
    assert ai_enhance.find_unsupported_spec_claims(
        f"{halved} 固态", allowed
    ) == [halved], "容量砍半属于量级级差异，不该被取整半径放过"


def test_explanation_with_an_unsupported_spec_value_is_dropped(catalog):
    """模型说了一个数据里没有的参数值——这条解读必须被丢掉。

    价格对得上但参数是编的，同样属于「断言没有依据的东西」。
    """

    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {
                        "overview": "总结",
                        "per_product": [
                            {"product_id": "LP001", "why": "续航 10 小时，够用"},
                            {"product_id": "LP002", "why": "整机仅 1.1 千克，很轻"},
                        ],
                    },
                    ensure_ascii=False,
                )
            ),
        )

    items = [_item(catalog.get("LP001")), _item(catalog.get("LP002"))]
    result = ai_enhance.explain_recommendations(
        Demand(category="laptop", budget=8000), items, service=make_service(handler)
    )

    assert "LP001" in result["per_product"], "有数据依据的解读被误杀了"
    assert "LP002" not in result["per_product"], "编造参数的解读没有被丢掉"
    assert "LP002" in result["dropped"]


def test_explanations_using_only_real_values_survive(catalog):
    """正例：解读里的数值全部能在数据里找到时，一条都不能被丢。

    这条防的是「校验过严」——价格校验当初就在这上面踩过坑。
    解读文本由**真实参数拼出来**，所以无论数据集怎么换都成立。
    """
    first = _real_specs(catalog, "LP001")
    second = _real_specs(catalog, "LP002")
    first_why = (
        f"{first['ram']:.0f}GB 内存配 {first['storage']:.0f}GB 固态，"
        f"{first['price']:.0f} 元"
    )
    second_why = f"续航约 {second['battery']:.0f} 小时，适合长时间使用"

    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {
                        "overview": "两件都在预算内",
                        "per_product": [
                            {"product_id": "LP001", "why": first_why},
                            {"product_id": "LP002", "why": second_why},
                        ],
                    },
                    ensure_ascii=False,
                )
            ),
        )

    items = [_item(catalog.get("LP001")), _item(catalog.get("LP002"))]
    result = ai_enhance.explain_recommendations(
        Demand(category="laptop", budget=8000), items, service=make_service(handler)
    )

    assert result["dropped"] == []
    assert set(result["per_product"]) == {"LP001", "LP002"}
    assert result["overview"], "总述不应被误丢"


def test_overview_with_an_unsupported_spec_value_is_dropped(catalog):
    """总述走同一条检查链，不能只查价格。"""

    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {
                        "overview": "这几款续航都在 20 小时以上",
                        "per_product": [
                            {"product_id": "LP001", "why": "续航 10 小时，够用"}
                        ],
                    },
                    ensure_ascii=False,
                )
            ),
        )

    result = ai_enhance.explain_recommendations(
        Demand(category="laptop", budget=8000),
        [_item(catalog.get("LP001"))],
        service=make_service(handler),
    )

    assert result["overview"] == "", "总述里的参数断言没有被校验"
    assert result["per_product"], "总述被丢不该影响逐条解读"


@pytest.mark.parametrize(
    "text, expected",
    [
        # 断言的维度在数据集里根本不存在 —— 抓住
        ("这款销量第一，值得买", ["销量第一"]),
        ("口碑最好的一款", ["口碑最好"]),
        ("续航在同类里遥遥领先", ["遥遥领先"]),
        ("全网最低价", ["全网最低"]),
        # 系统**确实**会排序，关于本次推荐的比较是真的 —— 不能误杀
        ("在本次推荐中排名第一", []),
        ("三款里它的评分最高", []),
        ("预算匹配度最高", []),
        # 正常有依据的表述
        ("续航 10 小时，通勤够用", []),
        ("性价比不错，适合学生", []),
        ("", []),
    ],
)
def test_find_unsupported_claims(text, expected):
    assert ai_enhance.find_unsupported_claims(text) == expected


def test_explanation_with_an_absolute_claim_is_dropped(catalog):
    """「销量第一」这类结论在数据里查无实据——该条必须被丢掉。

    数据集里没有销量、没有用户评价、没有行业排名，这些说法不可能从传入
    数据推出来，只能是从模型的先验知识里编的。
    """

    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {
                        "overview": "",
                        "per_product": [
                            {"product_id": "LP001", "why": "续航 10 小时，够用"},
                            {"product_id": "LP002", "why": "销量第一，闭眼买"},
                        ],
                    },
                    ensure_ascii=False,
                )
            ),
        )

    items = [_item(catalog.get("LP001")), _item(catalog.get("LP002"))]
    result = ai_enhance.explain_recommendations(
        Demand(category="laptop", budget=8000), items, service=make_service(handler)
    )

    assert "LP001" in result["per_product"]
    assert "LP002" not in result["per_product"], "排他性结论没有被丢掉"
    assert "LP002" in result["dropped"]


def test_ranking_language_about_this_recommendation_survives(catalog):
    """系统自己算出的排序结论不能被当成「排他性结论」误杀。

    这是本条校验最容易踩的坑：`排名第一` 四个字本身没问题——
    问题在于它断言的是**市场排名**还是**本次推荐内的排序**。
    保守起见只收明确指向外部维度的说法。
    """

    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {
                        "overview": "两款都在预算内，按匹配度排序如下",
                        "per_product": [
                            {"product_id": "LP001", "why": "在本次推荐中排名第一"},
                            {"product_id": "LP002", "why": "三款里评分最高"},
                        ],
                    },
                    ensure_ascii=False,
                )
            ),
        )

    items = [_item(catalog.get("LP001")), _item(catalog.get("LP002"))]
    result = ai_enhance.explain_recommendations(
        Demand(category="laptop", budget=8000), items, service=make_service(handler)
    )

    assert result["dropped"] == [], "有依据的排序表述被误杀"
    assert set(result["per_product"]) == {"LP001", "LP002"}


def test_overview_with_an_absolute_claim_is_dropped(catalog):
    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {
                        "overview": "这几款都是销量第一的爆款",
                        "per_product": [
                            {"product_id": "LP001", "why": "续航 10 小时，够用"}
                        ],
                    },
                    ensure_ascii=False,
                )
            ),
        )

    result = ai_enhance.explain_recommendations(
        Demand(category="laptop", budget=8000),
        [_item(catalog.get("LP001"))],
        service=make_service(handler),
    )

    assert result["overview"] == "", "总述里的排他性结论没有被校验"
    assert result["per_product"], "总述被丢不该影响逐条解读"


# --------------------------------------------------------------------------
# 存疑属性：模型不能就数据打架的地方下结论
# --------------------------------------------------------------------------


def _flagged_product() -> Product:
    """参数说没有独显、描述却说有——触发 R5，`has_dedicated_gpu` 被标记存疑。"""
    return Product(
        id="FLAG1",
        name="存疑笔记本",
        category="laptop",
        price=3999,
        brand="测试品牌",
        specs={"cpu_tier": 3, "has_dedicated_gpu": False, "battery_h": 10},
        use_cases=["办公"],
        pros=["带独立显卡，游戏有加成"],
        cons=["屏幕一般"],
        data_source="演示数据 · 测试夹具",
        updated_at="2026-01-01",
    )


def test_product_brief_carries_data_issues():
    """传给模型的商品摘要里要带上存疑说明，让它主动避开。"""
    product = _flagged_product()
    brief = ai_enhance._product_brief(
        product, rank=1, score_total=80.0, match_level="较为匹配",
        dimensions=[], budget_label="预算内",
    )

    assert brief["data_issues"], "存疑说明没有传给模型"
    assert "独立显卡" in brief["data_issues"][0]


def test_claim_about_a_flagged_attribute_is_dropped():
    """解读就存疑属性下结论——该条必须被丢掉。"""
    product = _flagged_product()
    assert product.data_issues, "夹具没有触发存疑标记"

    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {
                        "overview": "",
                        "per_product": [
                            {"product_id": "FLAG1", "why": "带独立显卡，游戏有加成"}
                        ],
                    },
                    ensure_ascii=False,
                )
            ),
        )

    result = ai_enhance.explain_recommendations(
        Demand(category="laptop", budget=6000),
        [_item(product)],
        service=make_service(handler),
    )

    assert result["per_product"] == {}, "就存疑属性下的结论没有被拦截"
    assert "FLAG1" in result["dropped"]


def test_claim_about_a_clean_attribute_survives():
    """同一件商品**没被标记**的属性照常解读——拦截不能株连整件商品。"""
    product = _flagged_product()
    assert product.data_issues, "夹具没有触发存疑标记"

    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {
                        "overview": "",
                        "per_product": [
                            {"product_id": "FLAG1", "why": "续航 10 小时，通勤够用"}
                        ],
                    },
                    ensure_ascii=False,
                )
            ),
        )

    result = ai_enhance.explain_recommendations(
        Demand(category="laptop", budget=6000),
        [_item(product)],
        service=make_service(handler),
    )

    assert "FLAG1" in result["per_product"], "未被标记的属性也被牵连了"
    assert result["dropped"] == []


@pytest.mark.parametrize(
    "field, expected_has_keyword",
    [
        ("has_dedicated_gpu", True),   # 有 SPEC_LABELS
        ("camera_tier", True),        # 标签「拍照档位」剥后缀 → 「拍照」
        ("cpu_tier", True),            # 标签「处理器档位」剥后缀 → 「处理器」
        ("price", True),               # 手工补的关键词
        ("pros", False),               # 无可靠文字特征，交提示词约束
    ],
)
def test_issue_keyword_derivation(field, expected_has_keyword):
    """被标记属性 → 关键词。取不到的属性返回空，交由提示词约束（保守优先）。"""
    assert bool(ai_enhance._issue_keywords(field)) is expected_has_keyword


def test_single_character_keywords_are_rejected():
    """单字关键词误杀风险太高，必须被过滤掉。"""
    assert all(len(kw) >= 2 for kw in ai_enhance._issue_keywords("camera_tier"))


# --------------------------------------------------------------------------
# 工具调用（tools / tool_calls）
# --------------------------------------------------------------------------


def _tool_call(name: str, arguments: str, *, call_id: str = "call_1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _tool_response(calls: list[dict], *, content: str = ""):
    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=content,
                message={"tool_calls": calls},
                finish_reason="tool_calls",
            ),
        )

    return make_service(handler)


TOOL_DECL = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "按条件筛选商品",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


def test_tools_are_sent_in_the_request_body():
    """传了 tools 就按 OpenAI 兼容格式带上，且请求仍经该模块统一发出。"""
    seen: dict = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=ok_body(content="好"))

    service = make_service(handler)
    service.complete("sys", "usr", tools=TOOL_DECL)

    assert seen["tools"] == TOOL_DECL


def test_request_omits_tools_when_not_provided():
    """不传 tools 时请求体里不出现该字段——既有调用行为完全不变。

    空列表在部分服务商上会被当成「不允许调用工具」，
    而这里是「这次不需要工具」，两者语义不同，所以是整个字段都不带。
    """
    seen: dict = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=ok_body(content="好"))

    make_service(handler).complete("sys", "usr")

    assert "tools" not in seen
    assert "tool_choice" not in seen


def test_tool_choice_is_forwarded_only_with_tools():
    seen: dict = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=ok_body(content="好"))

    make_service(handler).complete("sys", "usr", tools=TOOL_DECL, tool_choice="auto")
    assert seen["tool_choice"] == "auto"


def test_tool_calls_are_parsed_with_decoded_arguments():
    service = _tool_response(
        [_tool_call("search_products", '{"category": "headphone", "budget_max": 500}')]
    )
    response = service.complete("sys", "usr", tools=TOOL_DECL)

    assert response.wants_tools
    assert response.tool_calls[0].name == "search_products"
    assert response.tool_calls[0].arguments == {
        "category": "headphone",
        "budget_max": 500,
    }
    assert response.tool_calls[0].call_id == "call_1"


def test_empty_content_with_tool_calls_is_not_a_failure():
    """请求工具时 content 本来就是空的——**那不是失败，是模型在工作**。

    这一条如果写反了，工具调用永远走不通：模型每请求一次工具就被当成
    「返回了空内容」而报错降级。
    """
    service = _tool_response([_tool_call("get_product_detail", '{"product_id": "LP001"}')])
    response = service.complete("sys", "usr", tools=TOOL_DECL)

    assert response.content == ""
    assert response.wants_tools


def test_multiple_tool_calls_are_all_returned():
    service = _tool_response(
        [
            _tool_call("search_products", "{}", call_id="c1"),
            _tool_call("search_knowledge", '{"query": "降噪"}', call_id="c2"),
        ]
    )
    response = service.complete("sys", "usr", tools=TOOL_DECL)

    assert [call.name for call in response.tool_calls] == [
        "search_products",
        "search_knowledge",
    ]


def test_arguments_given_as_object_are_accepted():
    """有些服务商直接给对象而不是 JSON 字符串，一并接受。"""

    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content="",
                message={
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "search_products",
                                "arguments": {"category": "phone"},
                            },
                        }
                    ]
                },
                finish_reason="tool_calls",
            ),
        )

    response = make_service(handler).complete("sys", "usr", tools=TOOL_DECL)
    assert response.tool_calls[0].arguments == {"category": "phone"}


def test_missing_arguments_defaults_to_empty_object():
    """部分服务商在无参数时省略 arguments 字段。"""

    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content="",
                message={
                    "tool_calls": [
                        {"id": "c1", "type": "function", "function": {"name": "list"}}
                    ]
                },
                finish_reason="tool_calls",
            ),
        )

    response = make_service(handler).complete("sys", "usr", tools=TOOL_DECL)
    assert response.tool_calls[0].arguments == {}


@pytest.mark.parametrize(
    "bad_arguments",
    ['{"category": ', "不是 JSON", "[1, 2, 3]", '"字符串"', "123"],
)
def test_malformed_tool_arguments_raise_instead_of_half_parsing(bad_arguments):
    """参数解析不出来就报错降级，**不做「尽力修复」**。

    与 `complete_json` 同一立场：残缺的结果往下传，上层会当成有效数据用。
    """
    service = _tool_response([_tool_call("search_products", bad_arguments)])
    with pytest.raises(UpstreamResponseError):
        service.complete("sys", "usr", tools=TOOL_DECL)


@pytest.mark.parametrize(
    "entry",
    [
        {"id": "c1"},                                  # 缺 function
        {"id": "c1", "function": {}},                  # 缺 name
        {"function": {"name": "x", "arguments": "{}"}},  # 缺 id
        "不是对象",
    ],
)
def test_malformed_tool_call_entries_raise(entry):
    service = _tool_response([entry])
    with pytest.raises(UpstreamResponseError):
        service.complete("sys", "usr", tools=TOOL_DECL)


def test_tool_calls_not_a_list_raises():
    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content="",
                message={"tool_calls": "oops"},
                finish_reason="tool_calls",
            ),
        )

    with pytest.raises(UpstreamResponseError):
        make_service(handler).complete("sys", "usr", tools=TOOL_DECL)


def test_plain_answer_still_has_no_tool_calls():
    """普通作答路径不受影响：没有 tool_calls 字段时为空元组。"""
    response = make_service(
        lambda request: httpx.Response(200, json=ok_body(content="你好"))
    ).complete("sys", "usr")

    assert response.tool_calls == ()
    assert response.wants_tools is False


# --------------------------------------------------------------------------
# 知识问答作答
# --------------------------------------------------------------------------


def _passage(excerpt: str, *, title: str = "手机选购指南") -> "Passage":
    from src.knowledge.search import Passage

    return Passage(
        doc_id="category:phone",
        title=title,
        excerpt=excerpt,
        doc_type="category",
        type_label="品类级",
        source="本项目整理",
        updated_at="2026-10-15",
        score=12.0,
    )


def _answer_service(answer: str):
    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps({"answer": answer}, ensure_ascii=False)
            ),
        )

    return make_service(handler)


def test_answer_built_from_fragments_is_kept():
    passages = [_passage("主动降噪对低频有效，通勤路上主要受低频噪音困扰。")]
    answer = "通勤路上主要是低频噪音，主动降噪对它有效。"
    assert (
        ai_enhance.answer_from_knowledge(
            "手机拍照怎么选", passages, service=_answer_service(answer)
        )
        == answer
    )


def test_answer_may_repeat_a_price_that_appears_in_the_fragment():
    """片段里写过的参考价，回答里复述是允许的——它不是编的。"""
    passages = [_passage("参考价 1299 元。通勤场景优先看主动降噪。")]
    answer = "这款参考价 1299 元，通勤场景建议优先看主动降噪。"
    assert ai_enhance.answer_from_knowledge(
        "怎么选", passages, service=_answer_service(answer)
    )


def test_answer_with_an_invented_price_is_rejected():
    """数据里没有的价格一律拒绝——片段里根本没出现过这个数字。"""
    passages = [_passage("通勤场景优先看主动降噪能力。")]
    with pytest.raises(UpstreamResponseError):
        ai_enhance.answer_from_knowledge(
            "怎么选", passages, service=_answer_service("这款只要 299 元，很划算。")
        )


def test_answer_with_an_absolute_claim_is_rejected():
    """排他性结论与解读走同一张模式表。"""
    passages = [_passage("通勤场景优先看主动降噪能力。")]
    with pytest.raises(UpstreamResponseError):
        ai_enhance.answer_from_knowledge(
            "怎么选", passages, service=_answer_service("这款销量第一，闭眼买。")
        )


def test_empty_answer_is_rejected():
    passages = [_passage("通勤场景优先看主动降噪能力。")]
    with pytest.raises(UpstreamResponseError):
        ai_enhance.answer_from_knowledge(
            "怎么选", passages, service=_answer_service("   ")
        )


def test_no_fragments_is_rejected_without_calling_the_model():
    """没有片段就直接拒绝，**不发起请求**——没有依据就不该问模型。"""

    def handler(request):  # pragma: no cover —— 不该被调到
        raise AssertionError("没有片段时不应发起模型调用")

    with pytest.raises(UpstreamResponseError):
        ai_enhance.answer_from_knowledge(
            "怎么选", [], service=make_service(handler)
        )


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(500, json={"error": "boom"}),
        httpx.Response(401, json={"error": "bad key"}),
        httpx.Response(200, json=ok_body(content="这不是 JSON")),
        httpx.Response(200, json=ok_body(content="", finish_reason="length")),
    ],
)
def test_transport_failures_propagate_for_degradation(failure):
    """各种失败都抛领域异常，由界面降级为「只展示片段」。"""
    passages = [_passage("通勤场景优先看主动降噪能力。")]

    def handler(request):
        return failure

    with pytest.raises(ZhigouError):
        ai_enhance.answer_from_knowledge(
            "怎么选", passages, service=make_service(handler)
        )


def test_answer_is_whitespace_normalised():
    passages = [_passage("通勤场景优先看主动降噪能力。")]
    answer = ai_enhance.answer_from_knowledge(
        "怎么选", passages, service=_answer_service("  通勤\n\n优先看   主动降噪。  ")
    )
    assert answer == "通勤 优先看 主动降噪。"


def test_explanation_for_an_unknown_product_is_dropped(catalog):
    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {"overview": "", "per_product": [{"product_id": "不存在的ID", "why": "很好"}]},
                    ensure_ascii=False,
                )
            ),
        )

    result = ai_enhance.explain_recommendations(
        Demand(category="laptop"), [_item(catalog.get("LP001"))], service=make_service(handler)
    )
    assert result["per_product"] == {}


def test_overview_with_an_invented_price_is_dropped(catalog):
    def handler(request):
        return httpx.Response(
            200,
            json=ok_body(
                content=json.dumps(
                    {"overview": "这几件都不到 9999 元", "per_product": []},
                    ensure_ascii=False,
                )
            ),
        )

    result = ai_enhance.explain_recommendations(
        Demand(category="laptop"), [_item(catalog.get("LP001"))], service=make_service(handler)
    )
    assert result["overview"] == ""


def test_clean_explanations_survive(catalog):
    """没有编造内容的解读要原样留下，不能被丢掉或改写。"""
    weight = _real_specs(catalog)["weight"]
    why = f"重量 {weight}kg，适合每天通勤携带"

    def handler(request):
        return json_response(
            {
                "overview": "这三件都落在你的预算内。",
                "per_product": [{"product_id": "LP001", "why": why}],
            }
        )

    result = ai_enhance.explain_recommendations(
        Demand(category="laptop"), [_item(catalog.get("LP001"))], service=make_service(handler)
    )
    assert result["per_product"]["LP001"] == why
    assert result["overview"]


def test_explain_with_no_items_raises_instead_of_faking_output():
    with pytest.raises(UpstreamResponseError):
        ai_enhance.explain_recommendations(
            Demand(category="laptop"), [], service=make_service(lambda r: httpx.Response(200, json=ok_body()))
        )


# --------------------------------------------------------------------------
# 数据共享说明
# --------------------------------------------------------------------------


def test_data_sharing_notice_lists_what_is_sent():
    notice = ai_enhance.data_sharing_notice(
        Demand(category="laptop", budget=3000, raw_text="预算 3000 买笔记本"), item_count=5
    )

    assert "需求原文" in notice
    assert "5 件候选商品" in notice
    assert "不会发送" in notice
    assert FAKE_KEY not in notice


def test_data_sharing_notice_before_any_candidates_are_known():
    """分析之前不知道有几件候选，不能写「0 件」——那看起来像出错了。"""
    notice = ai_enhance.data_sharing_notice(Demand(category="laptop"), item_count=0)

    assert "0 件" not in notice
    assert "候选商品" in notice


# --------------------------------------------------------------------------
# 辅助
# --------------------------------------------------------------------------


def json_response(payload: dict) -> httpx.Response:
    return httpx.Response(
        200,
        json=ok_body(content=json.dumps(payload, ensure_ascii=False)),
    )


def _real_specs(catalog, product_id: str = "LP001") -> dict:
    """取一件笔记本**真实**的参数与价格，供数值断言当基准。

    基准从数据里现取，不写死。以前这里散落着一堆「LP001 重 1.28 千克、
    16GB 内存、3299 元」之类的字面量——数据集换成真实品牌之后它们全变了，
    而失败信息看起来像是幻觉检测失灵，其实是基准过期了。
    """
    product = catalog.get(product_id)
    assert product is not None, f"数据集里应当有 {product_id}"
    return {
        "weight": float(product.spec("weight_kg")),
        "battery": float(product.spec("battery_h")),
        "ram": float(product.spec("ram_gb")),
        "storage": float(product.spec("storage_gb")),
        "screen": float(product.spec("screen_size")),
        "price": float(product.price),
    }


def _item(product: Product):
    """把一个商品包成 RecommendationItem，评分用真实计算。"""
    from src.demand_parser import Demand as _Demand
    from src.recommender import RecommendationItem
    from src.scoring import score_product

    demand = _Demand(category=product.category, budget=8000)
    score = score_product(product, demand, [product])
    return RecommendationItem(product=product, score=score, within_budget=True)
