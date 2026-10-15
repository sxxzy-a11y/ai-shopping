"""编排循环、执行轨迹与降级的测试。

这个文件守三条线：

1. **循环受控**——有轮次上限、有终止条件，不会陷进无限循环
2. **轨迹是真的**——只记录发生过的调用，条数与实际调用次数一致，
   被拒的调用也如实入轨迹
3. **失败必降级**——任何一种失败都不能让分析中断或结果变空白
"""

from __future__ import annotations

import json

import httpx
import pytest

from src import ai_service, config, data_loader
from src.agent.registry import Tool, ToolContext, ToolRegistry
from src.agent.runner import AgentRun, TraceStep, run_agent
from src.agent.tools import TOOLS, build_registry
from src.errors import UpstreamTimeout, UpstreamUnavailable
from src.knowledge.corpus import build_corpus
from src.knowledge.index import BM25Index

FAKE_KEY = "sk-test-not-a-real-key-000000"


@pytest.fixture(scope="module")
def catalog():
    return data_loader.load_catalog()


@pytest.fixture(scope="module")
def index(catalog) -> BM25Index:
    return BM25Index(build_corpus(config.knowledge_dir(), catalog.products))


def _reply(content: str = "", tool_calls: list[dict] | None = None) -> httpx.Response:
    message: dict = {"role": "assistant", "content": content}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return httpx.Response(
        200,
        json={
            "model": "test-model",
            "choices": [
                {
                    "message": message,
                    "finish_reason": "tool_calls" if tool_calls else "stop",
                }
            ],
            "usage": {"total_tokens": 10},
        },
    )


def _call(name: str, arguments: dict, *, call_id: str = "c1") -> dict:
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


def _scripted_service(responses: list[httpx.Response]) -> ai_service.AIService:
    """按顺序返回预设响应的模型服务。用完之后重复最后一条。"""
    state = {"i": 0}

    def handler(request):
        index = min(state["i"], len(responses) - 1)
        state["i"] += 1
        return responses[index]

    return ai_service.AIService(
        api_key=FAKE_KEY,
        base_url="https://example.invalid/v1",
        model="test-model",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


# --------------------------------------------------------------------------
# 正常路径
# --------------------------------------------------------------------------


def test_model_answers_without_using_tools(catalog, index):
    """模型判断不需要工具时直接作答，一次调用都不发。"""
    service = _scripted_service([_reply("直接回答，不需要查数据。")])
    run = run_agent("你好", catalog=catalog, service=service, knowledge_index=index)

    assert run.answer == "直接回答，不需要查数据。"
    assert run.trace == ()
    assert run.used_tools is False
    assert run.rounds == 1
    assert run.degraded is False


def test_multi_step_task_runs_tools_in_order(catalog, index):
    service = _scripted_service(
        [
            _reply(tool_calls=[_call("search_products", {"category": "laptop", "budget_max": 5000})]),
            _reply(tool_calls=[_call("search_knowledge", {"query": "笔记本多重适合带出门"}, call_id="c2")]),
            _reply("综合来看，这几款适合编程。"),
        ]
    )
    run = run_agent(
        "预算 5000 编程，笔记本多重适合带出门",
        catalog=catalog, service=service, knowledge_index=index,
    )

    assert [step.tool for step in run.trace] == ["search_products", "search_knowledge"]
    assert [step.round for step in run.trace] == [1, 2]
    assert run.answer == "综合来看，这几款适合编程。"
    assert run.rounds == 3


def test_parallel_calls_in_one_round(catalog, index):
    """一轮里可以请求多个工具——这正是复合问题的形态。"""
    service = _scripted_service(
        [
            _reply(tool_calls=[
                _call("search_products", {"category": "phone", "budget_max": 3000}, call_id="a"),
                _call("search_knowledge", {"query": "手机怎么选"}, call_id="b"),
            ]),
            _reply("两边的结果合起来看……"),
        ]
    )
    run = run_agent("3000 以内手机怎么选", catalog=catalog, service=service, knowledge_index=index)

    assert len(run.trace) == 2
    assert {step.tool for step in run.trace} == {"search_products", "search_knowledge"}
    assert all(step.round == 1 for step in run.trace)


def test_tool_arguments_are_forwarded_verbatim(catalog, index):
    """轨迹里的参数是模型**原样给出的**，不是校验后的规范化结果。

    这一条很重要：看轨迹的人要能判断「模型给错了什么」，
    如果显示的是被规范化后的值，就看不到问题出在哪。
    """
    service = _scripted_service(
        [
            _reply(tool_calls=[_call("search_products", {"category": "laptop", "budget_max": 5000})]),
            _reply("好了"),
        ]
    )
    run = run_agent("问题", catalog=catalog, service=service, knowledge_index=index)

    assert run.trace[0].arguments == {"category": "laptop", "budget_max": 5000}


# --------------------------------------------------------------------------
# 终止条件（任务 3.7 / 3.9 / 3.10）
# --------------------------------------------------------------------------


def test_round_limit_stops_the_loop(catalog, index):
    """模型一直请求工具也不会无限跑下去。"""
    service = _scripted_service(
        [_reply(tool_calls=[_call("search_products", {"budget_max": 5000})])]
    )
    run = run_agent("问题", catalog=catalog, service=service, knowledge_index=index, max_rounds=3)

    assert run.rounds == 3
    assert len(run.trace) == 3
    assert run.degraded is True
    assert "3 轮" in run.degrade_reason
    assert run.answer == ""


def test_round_limit_respects_config_default(catalog, index):
    service = _scripted_service([_reply(tool_calls=[_call("search_products", {})])])
    run = run_agent("问题", catalog=catalog, service=service, knowledge_index=index)

    assert run.rounds == config.AGENT_MAX_ROUNDS


def test_timeout_propagates_for_degradation(catalog, index):
    """上游超时原样抛出，由调用方在边界处统一捕获降级。

    不在这里吞掉，是为了让整个项目只有一处处理上游异常的出口。
    """

    def handler(request):
        raise httpx.TimeoutException("simulated")

    service = ai_service.AIService(
        api_key=FAKE_KEY, base_url="https://example.invalid/v1", model="m",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(UpstreamTimeout):
        run_agent("问题", catalog=catalog, service=service, knowledge_index=index)


def test_upstream_failure_propagates(catalog, index):
    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    service = ai_service.AIService(
        api_key=FAKE_KEY, base_url="https://example.invalid/v1", model="m",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(UpstreamUnavailable):
        run_agent("问题", catalog=catalog, service=service, knowledge_index=index)


# --------------------------------------------------------------------------
# 轨迹（任务 4.4 / 4.5 / 4.6）
# --------------------------------------------------------------------------


def test_trace_length_matches_actual_calls(catalog, index):
    """轨迹条数 == 实际发生的调用次数。

    这条防的是「往里塞模型的思考文字」——那样轨迹会变长，
    而实际调用次数没有变。
    """
    service = _scripted_service(
        [
            _reply(tool_calls=[
                _call("search_products", {"category": "laptop"}, call_id="a"),
                _call("get_product_detail", {"product_id": "LP001"}, call_id="b"),
            ]),
            _reply("完成"),
        ]
    )
    run = run_agent("问题", catalog=catalog, service=service, knowledge_index=index)
    assert len(run.trace) == 2


def test_rejected_calls_are_recorded(catalog, index):
    """被参数校验拒绝的调用**同样入轨迹**。

    那恰恰是最有说服力的展示内容——证明校验真的在拦，不是摆设。
    """
    service = _scripted_service(
        [
            _reply(tool_calls=[_call("search_products", {"category": "平板"})]),
            _reply("类别不存在，我换个说法……"),
        ]
    )
    run = run_agent("问题", catalog=catalog, service=service, knowledge_index=index)

    step = run.trace[0]
    assert step.status == "rejected"
    assert step.status_label == "参数被拒"
    assert "平板" in step.summary


def test_unknown_tool_name_is_recorded_as_rejected(catalog, index):
    service = _scripted_service(
        [
            _reply(tool_calls=[_call("drop_everything", {})]),
            _reply("好的"),
        ]
    )
    run = run_agent("问题", catalog=catalog, service=service, knowledge_index=index)
    assert run.trace[0].status == "rejected"
    assert "drop_everything" in run.trace[0].summary


def test_no_tool_use_leaves_an_empty_trace(catalog, index):
    """没调工具就是空轨迹——**不是伪造的空步骤**，界面据此说明「本次未使用工具」。"""
    service = _scripted_service([_reply("直接答")])
    run = run_agent("问题", catalog=catalog, service=service, knowledge_index=index)
    assert run.trace == ()


def test_tool_internal_error_is_recorded_as_error(catalog, index):
    """工具执行出错与参数被拒在轨迹里是**两种状态**——一个该改代码，一个该改提示词。"""

    def _boom(params, ctx):
        raise RuntimeError("模拟内部错误")

    broken = Tool(
        name="search_products", description="x",
        params_model=TOOLS[0].params_model, run=_boom,
    )
    service = _scripted_service(
        [
            _reply(tool_calls=[_call("search_products", {"budget_max": 5000})]),
            _reply("换个方式"),
        ]
    )
    run = run_agent(
        "问题", catalog=catalog, service=service, knowledge_index=index,
        registry=ToolRegistry([broken]),
    )
    assert run.trace[0].status == "error"


def test_trace_step_labels_are_reader_friendly():
    step = TraceStep(round=1, tool="search_products", arguments={}, status="ok", summary="x")
    assert step.arguments_label == "（无参数）"
    assert step.status_label == "成功"


# --------------------------------------------------------------------------
# 编排细节
# --------------------------------------------------------------------------


def test_tool_declarations_are_sent_every_round(catalog, index):
    """每一轮都要带上工具声明——漏了模型就没法继续调工具。"""
    seen: list[bool] = []

    def handler(request):
        body = json.loads(request.content)
        seen.append("tools" in body)
        if len(seen) == 1:
            return _reply(tool_calls=[_call("search_products", {"budget_max": 5000})])
        return _reply("好了")

    service = ai_service.AIService(
        api_key=FAKE_KEY, base_url="https://example.invalid/v1", model="m",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    run_agent("问题", catalog=catalog, service=service, knowledge_index=index)
    assert seen == [True, True]


def test_tool_results_are_fed_back_to_the_model(catalog, index):
    """回灌的消息里必须带 role=tool 与对应的 tool_call_id，否则协议不成立。"""
    captured: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        captured.append(body)
        if len(captured) == 1:
            return _reply(tool_calls=[_call("get_product_detail", {"product_id": "LP001"})])
        return _reply("好了")

    service = ai_service.AIService(
        api_key=FAKE_KEY, base_url="https://example.invalid/v1", model="m",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    run_agent("问题", catalog=catalog, service=service, knowledge_index=index)

    second = captured[1]["messages"]
    roles = [message["role"] for message in second]
    assert roles == ["system", "user", "assistant", "tool"]

    tool_message = second[-1]
    assert tool_message["tool_call_id"] == "c1"
    assert "LP001" in tool_message["content"]

    assistant_message = second[-2]
    assert assistant_message["tool_calls"][0]["function"]["name"] == "get_product_detail"


def test_missing_knowledge_index_is_reported_not_faked(catalog):
    """没给索引时 `search_knowledge` 明确报告未加载，而不是返回错误结果。"""
    service = _scripted_service(
        [
            _reply(tool_calls=[_call("search_knowledge", {"query": "降噪"})]),
            _reply("知识库没加载"),
        ]
    )
    run = run_agent("问题", catalog=catalog, service=service, knowledge_index=None)
    assert run.trace[0].status == "rejected"
    assert "知识库" in run.trace[0].summary


def test_agent_run_is_immutable():
    """编排结果做成 frozen dataclass——它是执行记录，不该被后续改动。"""
    run = AgentRun(answer="x")
    with pytest.raises(Exception):
        run.answer = "y"  # type: ignore[misc]
