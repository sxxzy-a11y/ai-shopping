"""Agent 工具层与参数校验的测试。

这个文件守的是**模型与业务代码之间那道闸门**。模型给的参数一律不可信——
它完全可能编一个不存在的品类、一个不存在的商品 ID、或者一个负数预算。
这里要证明这些都会被拦住，而且拦得**有理由**：错误说明要能让模型下一轮改对，
只丢一句「参数错误」等于没拦。

同时守住一条硬边界：**工具集只读**。没有修改数据、写库或对外请求的工具。
"""

from __future__ import annotations

import pytest

from src import config, data_loader
from src.agent.registry import Tool, ToolContext, ToolRegistry, ToolResult
from src.agent.tools import TOOLS, build_registry
from src.knowledge.corpus import build_corpus
from src.knowledge.index import BM25Index


@pytest.fixture(scope="module")
def context() -> ToolContext:
    catalog = data_loader.load_catalog()
    index = BM25Index(build_corpus(config.knowledge_dir(), catalog.products))
    return ToolContext(catalog=catalog, knowledge_index=index)


@pytest.fixture(scope="module")
def registry() -> ToolRegistry:
    return build_registry()


def _call(registry: ToolRegistry, context: ToolContext, name: str, **args) -> ToolResult:
    return registry.invoke(name, args, context=context)


# --------------------------------------------------------------------------
# 注册表
# --------------------------------------------------------------------------


def test_four_tools_are_registered(registry: ToolRegistry):
    assert registry.names == [
        "search_products",
        "get_product_detail",
        "compare_products",
        "search_knowledge",
    ]


def test_declarations_use_openai_shape(registry: ToolRegistry):
    for declaration in registry.declarations():
        assert declaration["type"] == "function"
        function = declaration["function"]
        assert function["name"]
        assert function["description"], "没有描述的模型不知道什么时候该用它"
        assert function["parameters"]["type"] == "object"


def test_declaration_schema_derives_from_the_param_model(registry: ToolRegistry):
    """声明与校验**同源**——不会出现「声明说可选、校验说必填」的漂移。"""
    declaration = next(
        d for d in registry.declarations()
        if d["function"]["name"] == "search_products"
    )
    properties = declaration["function"]["parameters"]["properties"]
    assert "category" in properties
    assert "budget_max" in properties


def test_duplicate_tool_names_are_rejected():
    tool = Tool(
        name="dup",
        description="x",
        params_model=TOOLS[0].params_model,
        run=lambda params, ctx: ToolResult(ok=True, payload={}, summary=""),
    )
    with pytest.raises(ValueError):
        ToolRegistry([tool, tool])


def test_unknown_tool_is_rejected(registry: ToolRegistry, context: ToolContext):
    result = _call(registry, context, "drop_database")
    assert result.ok is False
    assert "drop_database" in result.error
    assert "search_products" in result.error, "要告诉模型有哪些可用的，它下一轮才能改对"


# --------------------------------------------------------------------------
# 工具集只读（任务 2.12）
# --------------------------------------------------------------------------


def test_registry_contains_no_write_tools(registry: ToolRegistry):
    """**没有任何工具能修改数据、写库或对外发起请求。**

    「禁止模型执行任意 SQL」在本项目里的答案比「禁止」更彻底：
    根本没有能执行 SQL 的工具。
    """
    forbidden = ("write", "save", "update", "delete", "insert", "drop", "exec", "sql")
    for name in registry.names:
        lowered = name.lower()
        assert not any(word in lowered for word in forbidden), f"{name} 看起来像写操作"


def test_tool_modules_do_not_import_network_libraries():
    """工具层不直接触网——所有对外调用都收在 ai_service 里。"""
    import pathlib

    for path in pathlib.Path("src/agent").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for banned in ("import httpx", "import requests", "import urllib", "socket."):
            assert banned not in source, f"{path.name} 里出现了 {banned}"


# --------------------------------------------------------------------------
# search_products
# --------------------------------------------------------------------------


def test_search_products_executes(registry, context):
    result = _call(
        registry, context, "search_products",
        category="phone", budget_max=2000, use_cases=["游戏"],
    )
    assert result.ok
    assert result.payload["products"], "应当有候选"
    assert result.payload["matched"] == len(result.payload["products"])
    assert result.summary


def test_search_products_may_omit_category(registry, context):
    assert _call(registry, context, "search_products", budget_max=2000).ok


def test_search_products_rejects_unknown_category(registry, context):
    result = _call(registry, context, "search_products", category="平板")
    assert result.ok is False
    assert "平板" in result.error
    assert "laptop" in result.error, "要列出可用类别"


@pytest.mark.parametrize("budget", [0, -1, -999])
def test_search_products_rejects_non_positive_budget(registry, context, budget):
    result = _call(registry, context, "search_products", budget_max=budget)
    assert result.ok is False
    assert "正数" in result.error


def test_search_products_rejects_inverted_range(registry, context):
    result = _call(
        registry, context, "search_products", budget_min=8000, budget_max=3000
    )
    assert result.ok is False
    assert "不能大于" in result.error


def test_search_products_rejects_out_of_range_limit(registry, context):
    assert _call(registry, context, "search_products", limit=0).ok is False
    assert _call(registry, context, "search_products", limit=99).ok is False


def test_search_products_reports_no_match_without_failing(registry, context):
    """筛不出商品**不是错误**，如实说明即可——模型据此可以放宽条件再试。"""
    result = _call(registry, context, "search_products", budget_max=1)
    assert result.ok
    assert result.payload["matched"] == 0
    assert result.payload["message"]


# --------------------------------------------------------------------------
# get_product_detail
# --------------------------------------------------------------------------


def test_get_product_detail_executes(registry, context):
    result = _call(registry, context, "get_product_detail", product_id="LP001")
    assert result.ok
    assert result.payload["product_id"] == "LP001"
    assert result.payload["price"] is not None
    assert "data_source" in result.payload


def test_get_product_detail_reports_data_quality(registry, context):
    """详情里带上缺失字段与存疑属性——让模型知道哪些地方不能下结论。"""
    result = _call(registry, context, "get_product_detail", product_id="LP001")
    assert "missing_fields" in result.payload
    assert "data_issues" in result.payload


@pytest.mark.parametrize("fake_id", ["不存在", "LP999", "", "'; DROP TABLE--"])
def test_get_product_detail_rejects_unknown_id(registry, context, fake_id):
    result = _call(registry, context, "get_product_detail", product_id=fake_id)
    assert result.ok is False
    assert "不存在" in result.error


# --------------------------------------------------------------------------
# compare_products
# --------------------------------------------------------------------------


def test_compare_products_executes(registry, context):
    result = _call(registry, context, "compare_products", product_ids=["LP001", "LP002"])
    assert result.ok
    assert len(result.payload["products"]) == 2
    assert result.payload["differing_dimensions"], "跨两档配置应当有差异维度"


@pytest.mark.parametrize("count", [0, 1])
def test_compare_products_rejects_too_few(registry, context, count):
    result = _call(registry, context, "compare_products", product_ids=["LP001"] * count)
    assert result.ok is False


def test_compare_products_rejects_too_many(registry, context):
    ids = [p.id for p in context.catalog.products[: config.MAX_COMPARE_COUNT + 1]]
    assert _call(registry, context, "compare_products", product_ids=ids).ok is False


def test_compare_products_rejects_duplicates(registry, context):
    result = _call(registry, context, "compare_products", product_ids=["LP001", "LP001"])
    assert result.ok is False
    assert "重复" in result.error


def test_compare_products_rejects_unknown_id(registry, context):
    result = _call(
        registry, context, "compare_products", product_ids=["LP001", "编造的ID"]
    )
    assert result.ok is False
    assert "编造的ID" in result.error


def test_compare_products_rejects_mixed_categories(registry, context):
    """跨类别比较由业务层拒绝，工具如实转述原因。"""
    result = _call(registry, context, "compare_products", product_ids=["LP001", "PH001"])
    assert result.ok is False
    assert "类别" in result.error


# --------------------------------------------------------------------------
# search_knowledge
# --------------------------------------------------------------------------


def test_search_knowledge_executes(registry, context):
    result = _call(
        registry, context, "search_knowledge",
        query="处理器档位是什么意思",
    )
    assert result.ok
    assert result.payload["found"] >= 1
    assert result.payload["passages"][0]["content"]


def test_search_knowledge_out_of_corpus_is_not_an_error(registry, context):
    """检索不到**不是错误**——如实说明，模型据此可以说「资料里没提到」。"""
    result = _call(registry, context, "search_knowledge", query="今天天气怎么样")
    assert result.ok
    assert result.payload["found"] == 0


def test_search_knowledge_without_index_fails_clearly(registry):
    result = registry.invoke(
        "search_knowledge", {"query": "x"}, context=ToolContext(catalog=data_loader.load_catalog())
    )
    assert result.ok is False
    assert "知识库" in result.error


def test_search_knowledge_rejects_blank_query(registry, context):
    assert _call(registry, context, "search_knowledge", query="   ").ok is False


# --------------------------------------------------------------------------
# 校验失败的共同要求
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, args",
    [
        ("search_products", {"category": "平板"}),
        ("search_products", {"budget_max": -1}),
        ("get_product_detail", {"product_id": "不存在"}),
        ("compare_products", {"product_ids": ["LP001"]}),
        ("search_knowledge", {"query": "  "}),
        ("没这个工具", {}),
    ],
)
def test_failures_are_results_not_exceptions(registry, context, name, args):
    """校验失败返回结果而不是抛异常——编排循环要把原因回灌给模型。

    抛异常会直接中断整轮编排，模型连「改一次再试」的机会都没有。
    """
    result = registry.invoke(name, args, context=context)
    assert isinstance(result, ToolResult)
    assert result.ok is False
    assert result.error, "失败必须带原因，否则模型无从改起"
    assert result.summary, "失败也要有摘要——它要进执行轨迹"


def test_tool_internal_error_becomes_a_failure_result(monkeypatch, registry, context):
    """工具内部抛异常时转成失败结果，不顺着调用栈炸出去。"""

    def _boom(params, ctx):
        raise RuntimeError("模拟工具内部错误")

    broken = Tool(
        name="broken",
        description="测试用",
        params_model=TOOLS[0].params_model,
        run=_boom,
    )
    result = ToolRegistry([broken]).invoke("broken", {}, context=context)
    assert result.ok is False
    assert "RuntimeError" in result.error


def test_validation_error_names_the_offending_field(registry, context):
    """错误说明要点出**是哪个字段**错了——那是模型改对话术的唯一线索。"""
    result = _call(registry, context, "get_product_detail", product_id=None)
    assert result.ok is False
    assert "product_id" in result.error
