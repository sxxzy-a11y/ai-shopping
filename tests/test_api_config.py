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


def test_save_tightens_file_permissions(tmp_path: Path, monkeypatch):
    """密钥明文落盘，写入时必须尝试把文件权限收到 0600。

    用打桩验证「确实调用了 chmod」而不是断言 POSIX 权限位——后者在 Windows
    上恒为宽松值，跨平台测试会假失败。
    """
    called: list[int] = []
    original_chmod = Path.chmod

    def spy(self: Path, mode: int):
        called.append(mode)
        return original_chmod(self, mode)

    monkeypatch.setattr(Path, "chmod", spy)
    path = tmp_path / "api.json"
    api_config.save({"llm_api_key": "sk-secret-value"}, path=path)

    assert 0o600 in called, "写入含密钥的配置时没有收紧文件权限"
    assert api_config.load(path)["llm_api_key"] == "sk-secret-value"


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
