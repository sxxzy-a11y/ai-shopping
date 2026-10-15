"""配置层的不变量测试。

这里只放**跨模块的配置约束**，不放业务行为（业务行为在各自的测试文件里）。

最要紧的是默认端点与 `.env.example` 的绑定：二者一旦漂移，漏配环境变量的
部署会**静默打向另一个服务商**——请求会失败，但报错信息里看不出「打错了
地址」，而且本地演示模式完全正常，只有真去调模型时才暴露。
用测试把两边锁死，以后改任何一边忘另一边，测试立刻失败。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src import config
from src.ai_service import AIService


def _parse_env_example(path: Path) -> dict[str, str]:
    """把 `.env.example` 解析成键值字典。忽略注释与空行。"""
    pairs: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        pairs[key.strip()] = value.strip()
    return pairs


@pytest.fixture
def env_example() -> dict[str, str]:
    path = config.PROJECT_ROOT / ".env.example"
    assert path.exists(), f"缺少环境变量样例文件：{path}"
    return _parse_env_example(path)


@pytest.fixture
def no_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清空所有大模型环境变量，让配置回落到代码内置的默认值。"""
    for name in (
        config.LLM_API_KEY_ENV,
        config.LLM_BASE_URL_ENV,
        config.LLM_MODEL_ENV,
        config.LLM_TIMEOUT_ENV,
        config.LLM_MAX_TOKENS_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


# --------------------------------------------------------------------------
# 默认值与 .env.example 的绑定
# --------------------------------------------------------------------------


def test_default_base_url_matches_env_example(env_example: dict[str, str]):
    """默认端点必须等于 `.env.example` 登记的值。

    不硬编码期望值——那样只是把同一个常量抄两遍。这里解析样例文件，
    让「改了一边忘另一边」直接变成测试失败。
    """
    assert config.DEFAULT_LLM_BASE_URL == env_example[config.LLM_BASE_URL_ENV]


def test_default_model_matches_env_example(env_example: dict[str, str]):
    """默认模型名必须等于 `.env.example` 登记的值。"""
    assert config.DEFAULT_LLM_MODEL == env_example[config.LLM_MODEL_ENV]


def test_defaults_do_not_point_at_a_third_party(env_example: dict[str, str]):
    """默认端点与样例端点必须是同一个服务商。

    这条防止有人把默认值改回 `api.openai.com` 而样例文件仍是 DeepSeek——
    两个断言分开看都「没写错」，合起来却指向两家不同的服务。
    """
    default_host = config.DEFAULT_LLM_BASE_URL.split("//")[-1].split("/")[0]
    example_host = env_example[config.LLM_BASE_URL_ENV].split("//")[-1].split("/")[0]
    assert default_host == example_host


# --------------------------------------------------------------------------
# 未配置环境变量时的回落行为
# --------------------------------------------------------------------------


def test_getters_fall_back_to_defaults(no_llm_env: None):
    """未配置任何环境变量时，取值函数返回内置默认值。"""
    assert config.llm_base_url() == config.DEFAULT_LLM_BASE_URL
    assert config.llm_model() == config.DEFAULT_LLM_MODEL


def test_service_uses_defaults_and_reports_unconfigured(no_llm_env: None):
    """未配置密钥时，服务对象仍采用默认端点，且明确报告「未配置」。

    这一条同时守两件事：默认值确实被用上了，以及缺密钥时 `configured`
    为 False——界面据此走本地降级，而不是拿默认端点发一次注定失败的请求。
    """
    service = AIService()
    assert service.describe()["base_url"] == config.DEFAULT_LLM_BASE_URL
    assert service.model == config.DEFAULT_LLM_MODEL
    assert service.configured is False


def test_env_vars_still_win_over_defaults(
    monkeypatch: pytest.MonkeyPatch, no_llm_env: None
):
    """环境变量优先于默认值——换服务商不需要改代码。"""
    monkeypatch.setenv(config.LLM_BASE_URL_ENV, "https://example.invalid/v1")
    monkeypatch.setenv(config.LLM_MODEL_ENV, "some-other-model")
    assert config.llm_base_url() == "https://example.invalid/v1"
    assert config.llm_model() == "some-other-model"
