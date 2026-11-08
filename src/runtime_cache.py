"""进程内运行时缓存：商品数据集、知识检索索引、向量库。

为什么单独一层：这几个函数原先放在 `src/ui/state.py`，用 `st.cache_resource`
实现。Vue 版（`backend/`）只是想复用缓存，却不得不
`from src.ui.state import ...` —— 而那个模块第一行就 `import streamlit`，
于是一个**根本不跑 Streamlit** 的服务端进程被迫拖进整个框架（本机测得
site-packages 里 streamlit 占 28MB，连同 pyarrow / altair 等传递依赖更多）。

换成标准库 `functools.lru_cache` 之后：

- 两种界面共享同一份实现，缓存语义一致；
- 后端进程不再 import streamlit，部署可以只装 `requirements-vue.txt`；
- 缓存键仍是「路径 + 文件 mtime」，改库或改语料后自动重建，不需要重启。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src import config
from src.data_loader import Catalog, load_catalog
from src.knowledge.corpus import build_corpus
from src.knowledge.index import BM25Index


def _file_stamp(path: Path) -> float:
    """取文件修改时间；文件不在或读不到时返回 0（缓存键仍可用）。"""
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


@lru_cache(maxsize=4)
def _load_cached(path_str: str, _mtime: float) -> Catalog:
    """按「数据库路径 + 数据库文件修改时间」缓存数据集。

    `_mtime` 不参与计算，只用来构造缓存键：商品库被写入后 mtime 会变，
    下一次取数据集就自动换成新内容，不需要重启应用。
    `maxsize=4` 与原先的 `max_entries=4` 一致——旧版本的缓存没有复用价值。
    """
    return load_catalog(Path(path_str))


def get_catalog() -> Catalog:
    """取商品数据集。

    这里**不吞异常**——数据库损坏、库空且种子缺失等情况让领域异常抛出去，
    由调用方在边界处统一转成中文提示，保证异常处理只有一个出口。
    """
    path = config.products_db_path()
    return _load_cached(str(path), _file_stamp(path))


def _knowledge_stamp(directory: Path) -> float:
    """语料目录的变更印戳。

    目录自身的 mtime **只在增删文件时变，改内容不会变**——只取目录会让
    「编辑了一份指南」这种最常见的改动无法触发重建。所以把目录下所有
    `.md` 的 mtime 一并取最大值。
    """
    stamps = [_file_stamp(directory)]
    try:
        stamps.extend(_file_stamp(path) for path in directory.rglob("*.md"))
    except OSError:  # 目录不存在或读不了——保持可用，走空语料的分支
        pass
    return max(stamps, default=0.0)


@lru_cache(maxsize=4)
def _load_index_cached(
    dir_str: str, _knowledge_mtime: float, _products_mtime: float
) -> BM25Index:
    """按「语料目录 + 语料 mtime + 商品数据 mtime」缓存检索索引。

    商品数据也要进缓存键：商品级知识条目是由商品字段**合成**的，
    改了商品而语料没动时，索引同样需要重建。
    后两个参数不参与计算，只用于构造缓存键。
    """
    documents = build_corpus(Path(dir_str), get_catalog().products)
    return BM25Index(documents)


def get_knowledge_index() -> BM25Index:
    """取知识检索索引。改语料或改商品数据后自动重建，不需要重启应用。"""
    directory = config.knowledge_dir()
    return _load_index_cached(
        str(directory),
        _knowledge_stamp(directory),
        # 商品已迁入 SQLite：缓存键必须盯商品库文件，而不是种子 JSON——
        # 否则在界面改完商品参数/亮点/不足，知识检索仍是旧内容。
        _file_stamp(config.products_db_path()),
    )


def get_vector_store():
    """取向量库（SQLite 表）。轻量对象，每次新建即可。"""
    from src.knowledge.vector_store import VectorStore

    return VectorStore()


def clear_caches() -> int:
    """清空进程内缓存，返回清掉的缓存数。

    「重建索引」用它：清掉之后下一次 `get_knowledge_index()` 会按文件 mtime
    重新构建。返回数量是为了让接口能把结果如实报给界面。
    """
    cleared = 0
    for cached in (_load_cached, _load_index_cached):
        cached.cache_clear()
        cleared += 1
    return cleared
