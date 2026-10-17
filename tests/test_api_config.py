"""本机 API 覆盖配置的读写与脱敏。"""

from __future__ import annotations

from pathlib import Path

from src import api_config


def test_missing_file_returns_empty(tmp_path: Path):
    assert api_config.load(tmp_path / "nope.json") == {}


def test_corrupt_file_falls_back_to_empty(tmp_path: Path):
    path = tmp_path / "api.json"
    path.write_text("{ not json", encoding="utf-8")
    assert api_config.load(path) == {}


def test_save_and_load_round_trip(tmp_path: Path):
    path = tmp_path / "api.json"
    api_config.save({"llm_model": "deepseek-chat"}, path=path)
    api_config.save({"llm_base_url": "https://example.invalid/v1"}, path=path)

    loaded = api_config.load(path)
    assert loaded["llm_model"] == "deepseek-chat"
    assert loaded["llm_base_url"] == "https://example.invalid/v1"


def test_empty_values_do_not_overwrite(tmp_path: Path):
    path = tmp_path / "api.json"
    api_config.save({"llm_api_key": "sk-existing-1234567890"}, path=path)

    api_config.save({"llm_api_key": "", "llm_model": "new-model"}, path=path)

    loaded = api_config.load(path)
    assert loaded["llm_api_key"] == "sk-existing-1234567890", "留空不应清掉已有密钥"
    assert loaded["llm_model"] == "new-model"


def test_unknown_keys_are_ignored(tmp_path: Path):
    path = tmp_path / "api.json"
    api_config.save({"evil": "x", "llm_model": "m"}, path=path)

    loaded = api_config.load(path)
    assert "evil" not in loaded
    assert loaded["llm_model"] == "m"


def test_clear_removes_the_file(tmp_path: Path):
    path = tmp_path / "api.json"
    api_config.save({"llm_model": "m"}, path=path)
    assert path.exists()

    api_config.clear(path)

    assert not path.exists()
    assert api_config.load(path) == {}


def test_mask_never_returns_the_full_key():
    key = "sk-ws-H.PYILREX.Osb8.MEUCIQ-long-signature"
    masked = api_config.mask(key)
    assert key not in masked
    assert "****" in masked


def test_source_reports_where_the_value_comes_from(tmp_path: Path, monkeypatch):
    path = tmp_path / "api.json"
    monkeypatch.delenv("ZHIGOU_LLM_MODEL", raising=False)

    assert api_config.source_of("llm_model", path) == "默认值"
    api_config.save({"llm_model": "from-file"}, path=path)
    assert api_config.source_of("llm_model", path) == "本机配置"
