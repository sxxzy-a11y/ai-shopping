"""本机 API 配置覆盖文件。

界面（项目说明页）里修改的端点/模型/密钥写在这里；读取顺序为
**本机覆盖文件 > 环境变量 > 内置默认值**（见 `config` 的各 getter）。

为什么用独立 JSON 而不是回写 `.env`：
- 回写用户文件要处理注释、引号、编码，任何一处破坏都会让整个配置失效
- 独立文件删除即恢复环境变量配置，语义干净

安全说明：这是**演示级**存储——密钥明文落盘，仅限本机使用。
文件已加入 `.gitignore`；界面与日志均不回显明文。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from src.errors import ZhigouError

#: 允许由界面覆盖的键。白名单之外的一律忽略——避免任意写文件。
ALLOWED_KEYS: tuple[str, ...] = (
    "llm_api_key",
    "llm_base_url",
    "llm_model",
    "embedding_api_key",
    "embedding_base_url",
    "embedding_model",
    "embedding_dim",
)

#: 配置文件的路径环境变量。测试用它把文件指到临时目录。
PATH_ENV = "ZHIGOU_API_CONFIG_PATH"


def config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    raw = os.environ.get(PATH_ENV, "").strip()
    if raw:
        return Path(raw)
    from src import config

    return config.PROJECT_ROOT / "storage" / "api_config.json"


class ApiConfigError(ZhigouError):
    """读写本机配置失败。"""


def load(path: Path | None = None) -> dict[str, str]:
    """读取覆盖配置。

    **不抛异常**：文件缺失、损坏或不是对象时返回空字典，应用继续用
    环境变量与默认值——这份文件只影响配置便利性，不该中断启动。
    """
    target = config_path(path)
    if not target.is_file():
        return {}
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        key: str(value).strip()
        for key, value in raw.items()
        if key in ALLOWED_KEYS and str(value).strip()
    }


def get(key: str, path: Path | None = None) -> str:
    """取某一项覆盖值；没有则返回空字符串。"""
    if key not in ALLOWED_KEYS:
        return ""
    return load(path).get(key, "")


def save(
    values: dict[str, str | int | None], path: Path | None = None
) -> Path:
    """合并保存：只写入非空值，未提供的键保持不变。

    **空值不覆盖**是刻意的：用户在界面只改模型名时，密钥输入框留空，
    不能因此把已有密钥清掉。
    """
    target = config_path(path)
    merged = load(path)
    for key, value in values.items():
        if key not in ALLOWED_KEYS or value is None:
            continue
        text = str(value).strip()
        if text:
            merged[key] = text

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    try:
        tmp.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, target)
    except OSError as exc:
        raise ApiConfigError(
            "本机 API 配置写入失败，请检查 storage 目录是否可写。"
        ) from exc
    return target


def clear(path: Path | None = None) -> None:
    """删除覆盖文件——配置回退到环境变量与默认值。"""
    target = config_path(path)
    try:
        target.unlink(missing_ok=True)
    except OSError as exc:
        raise ApiConfigError("本机 API 配置清除失败。") from exc


def mask(value: str) -> str:
    """密钥脱敏：只保留头尾少量字符。"""
    if not value:
        return "未配置"
    if len(value) <= 10:
        return "已配置"
    return f"{value[:5]}****{value[-4:]}"


def source_of(key: str, path: Path | None = None) -> str:
    """这一项当前来自哪里：覆盖文件 / 环境变量 / 默认值。"""
    if key in ALLOWED_KEYS and load(path).get(key):
        return "本机配置"
    env_names = {
        "llm_api_key": "ZHIGOU_LLM_API_KEY",
        "llm_base_url": "ZHIGOU_LLM_BASE_URL",
        "llm_model": "ZHIGOU_LLM_MODEL",
        "embedding_api_key": "ZHIGOU_EMBEDDING_API_KEY",
        "embedding_base_url": "ZHIGOU_EMBEDDING_BASE_URL",
        "embedding_model": "ZHIGOU_EMBEDDING_MODEL",
        "embedding_dim": "ZHIGOU_EMBEDDING_DIM",
    }
    if os.environ.get(env_names.get(key, ""), "").strip():
        return "环境变量"
    return "默认值"
