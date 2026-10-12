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
    def handler(request):
        return json_response(
            {
                "overview": "这三件都落在你的预算内。",
                "per_product": [
                    {"product_id": "LP001", "why": "重量 1.28kg，适合每天通勤携带"},
                ],
            }
        )

    result = ai_enhance.explain_recommendations(
        Demand(category="laptop"), [_item(catalog.get("LP001"))], service=make_service(handler)
    )
    assert result["per_product"]["LP001"].startswith("重量 1.28kg")
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


def _item(product: Product):
    """把一个商品包成 RecommendationItem，评分用真实计算。"""
    from src.demand_parser import Demand as _Demand
    from src.recommender import RecommendationItem
    from src.scoring import score_product

    demand = _Demand(category=product.category, budget=8000)
    score = score_product(product, demand, [product])
    return RecommendationItem(product=product, score=score, within_budget=True)
