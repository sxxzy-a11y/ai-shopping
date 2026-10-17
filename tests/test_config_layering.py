"""配置分层：本机覆盖 > 环境变量 > 默认值。"""

from __future__ import annotations

from pathlib import Path

from src import ai_service, api_config, config


def test_file_override_wins_over_environment(tmp_path: Path, monkeypatch):
    path = tmp_path / "api.json"
    monkeypatch.setenv(api_config.PATH_ENV, str(path))
    monkeypatch.setenv(config.LLM_API_KEY_ENV, "sk-env-key-1234567890")
    monkeypatch.setenv(config.LLM_MODEL_ENV, "env-model")
    ai_service.get_service()  # 确认构造不报错

    api_config.save(
        {"llm_api_key": "sk-file-key-1234567890", "llm_model": "file-model"},
        path=path,
    )

    assert config.llm_api_key() == "sk-file-key-1234567890"
    assert config.llm_model() == "file-model"


def test_falls_back_to_environment_when_file_absent(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(api_config.PATH_ENV, str(tmp_path / "missing.json"))
    monkeypatch.setenv(config.EMBEDDING_MODEL_ENV, "env-embed")

    assert config.embedding_model() == "env-embed"


def test_clearing_file_restores_environment(tmp_path: Path, monkeypatch):
    path = tmp_path / "api.json"
    monkeypatch.setenv(api_config.PATH_ENV, str(path))
    monkeypatch.setenv(config.LLM_MODEL_ENV, "env-model")
    api_config.save({"llm_model": "file-model"}, path=path)

    api_config.clear(path)

    assert config.llm_model() == "env-model"


def test_embedding_dim_override_is_parsed_as_int(tmp_path: Path, monkeypatch):
    path = tmp_path / "api.json"
    monkeypatch.setenv(api_config.PATH_ENV, str(path))

    api_config.save({"embedding_dim": "768"}, path=path)

    assert config.embedding_dim() == 768
