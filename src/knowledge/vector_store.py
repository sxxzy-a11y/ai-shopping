"""知识切片向量库。

「向量库」在这里 = 一张 SQLite 表 + numpy 余弦检索：
语料规模百级，暴力计算毫秒级；少一个外部服务就少一类现场故障。
对外接口保持窄（`build_index` / `search` / `stats`），将来换 Chroma 时
只替换本模块，检索调度与界面不动。

一行 = 一个切片的向量。状态判定集中在 `stats()`：
- **可用**：正文哈希、模型、维度都与当前一致
- **过期**：行存在，但正文哈希或模型/维度已变
- **未生成**：当前切片没有对应行
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from src import config
from src.database import connect
from src.errors import ZhigouError
from src.knowledge.chunking import Slice
from src.knowledge.embeddings import EmbeddingService

logger = logging.getLogger("zhigou.knowledge.vector")


@dataclass(frozen=True)
class _MatrixEntry:
    """进程内缓存的一份「切片行 + 向量矩阵」快照。

    `VectorStore` 在界面层是每次新建的轻量对象（见 `state.get_vector_store`），
    所以缓存必须挂在模块上才能跨请求复用。`stamp` 是库文件的纳秒级修改时间，
    用来判断外部改动是否已让缓存过期。
    """

    rows: tuple[dict, ...]
    matrix: np.ndarray
    stamp: int


#: key = (库文件路径, 模型, 维度)。不同模型/维度绝不共用同一份矩阵。
#: 上限防止频繁切换配置时无限增长；淘汰最旧的一条即可，重建成本很低。
_MATRIX_CACHE: dict[tuple[str, str, int], _MatrixEntry] = {}
_MATRIX_CACHE_MAX_ENTRIES = 8

_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_vectors (
    doc_id       TEXT NOT NULL,
    slice_id     TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    heading      TEXT NOT NULL DEFAULT '',
    content      TEXT NOT NULL,
    doc_type     TEXT NOT NULL DEFAULT '',
    source       TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL DEFAULT '',
    product_id   TEXT NOT NULL DEFAULT '',
    model        TEXT NOT NULL,
    dim          INTEGER NOT NULL,
    embedding    TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    indexed_at   TEXT NOT NULL,
    PRIMARY KEY (doc_id, slice_id)
);
CREATE INDEX IF NOT EXISTS idx_knowledge_vectors_model
    ON knowledge_vectors (model, dim);
"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def content_hash(slice_: Slice) -> str:
    """向量化文本的指纹。正文、标题、小节任一变化都会变。"""
    return hashlib.sha256(slice_.embedding_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScoredSlice:
    """一条语义检索命中。"""

    slice: Slice
    score: float


@dataclass(frozen=True)
class IndexStats:
    """索引概览。"""

    total_slices: int
    ready: int
    stale: int
    missing: int
    model: str
    dim: int
    last_indexed_at: str

    @property
    def generation_needed(self) -> int:
        """待生成的切片数（过期 + 未生成）。"""
        return self.stale + self.missing


@dataclass(frozen=True)
class BuildResult:
    embedded: int
    skipped: int
    removed: int


class VectorStore:
    """切片的向量存储与近邻检索。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    # -- 基础 ------------------------------------------------------------

    def _ensure(self) -> None:
        with connect(self._path) as connection:
            connection.executescript(_SCHEMA)
            connection.commit()

    def _rows(self) -> list[dict]:
        self._ensure()
        with connect(self._path) as connection:
            cursor = connection.execute("SELECT * FROM knowledge_vectors")
            return [dict(row) for row in cursor.fetchall()]

    def _db_path(self) -> Path:
        """与 `database.connect` 用同一套路径解析，保证缓存键指向真实文件。"""
        return Path(self._path) if self._path is not None else config.database_path()

    @staticmethod
    def _stamp(path: Path) -> int:
        """库文件的纳秒级修改时间；读不到时返回 0（缓存键仍可用）。"""
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return 0

    def _invalidate(self) -> None:
        """写库后主动丢弃本库的全部缓存条目。

        只靠 mtime 不够：部分文件系统的时间精度较粗，一次 `build_index` 与紧随
        其后的 `search` 可能落在同一个时间刻度上，只读 mtime 会拿到旧矩阵。
        """
        prefix = str(self._db_path())
        for key in [key for key in _MATRIX_CACHE if key[0] == prefix]:
            del _MATRIX_CACHE[key]

    def _matrix(self, *, model: str, dim: int) -> tuple[tuple[dict, ...], np.ndarray]:
        """取「行 + 向量矩阵」，按库文件 mtime 缓存。

        原先每次 `search` 都要全表读出并逐行 `json.loads`；语料上到千级切片时
        这是检索链路里最重的一步。缓存后同一次运行内只解析一次。

        损坏行（非法 JSON、维度不符、含 NaN/inf）逐行跳过并记 warning，不让
        单条坏数据把整条语义检索打回关键词模式。
        """
        path = self._db_path()
        key = (str(path), model, dim)
        cached = _MATRIX_CACHE.get(key)
        if cached is not None and cached.stamp == self._stamp(path):
            return cached.rows, cached.matrix

        rows: list[dict] = []
        vectors: list[list[float]] = []
        for row in self._rows():
            try:
                if row["model"] != model or int(row["dim"]) != dim:
                    continue
                parsed = json.loads(row["embedding"])
                if not isinstance(parsed, list) or len(parsed) != dim:
                    raise ValueError(f"期望 {dim} 维，实际不是该长度的列表")
                values = [float(value) for value in parsed]
                if not all(math.isfinite(value) for value in values):
                    raise ValueError("含 NaN 或无穷大")
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "跳过损坏的向量行 %s/%s：%s",
                    row.get("doc_id", "?"),
                    row.get("slice_id", "?"),
                    exc,
                )
                continue
            rows.append(row)
            vectors.append(values)

        matrix = (
            np.asarray(vectors, dtype=np.float32)
            if vectors
            else np.empty((0, dim), dtype=np.float32)
        )
        # `_rows()` 里的 _ensure 可能刚创建库文件，戳要在读完之后重新取。
        entry = _MatrixEntry(rows=tuple(rows), matrix=matrix, stamp=self._stamp(path))
        if len(_MATRIX_CACHE) >= _MATRIX_CACHE_MAX_ENTRIES:
            _MATRIX_CACHE.pop(next(iter(_MATRIX_CACHE)))
        _MATRIX_CACHE[key] = entry
        logger.debug("向量矩阵已重建：%d 行，model=%s dim=%d", len(rows), model, dim)
        return entry.rows, entry.matrix

    # -- 索引 ------------------------------------------------------------

    def build_index(
        self,
        slices: list[Slice],
        *,
        service: EmbeddingService,
        progress: Callable[[int, int], None] | None = None,
    ) -> BuildResult:
        """增量生成向量。

        Raises:
            领域异常（来自 EmbeddingService），调用方据此提示失败。
        """
        self._ensure()
        existing = {(row["doc_id"], row["slice_id"]): row for row in self._rows()}

        pending: list[Slice] = []
        skipped = 0
        for slice_ in slices:
            row = existing.get((slice_.doc_id, slice_.slice_id))
            if (
                row
                and row["content_hash"] == content_hash(slice_)
                and row["model"] == service.model
                and int(row["dim"]) == service.dim
            ):
                skipped += 1
                continue
            pending.append(slice_)

        embedded = 0
        if pending:
            vectors = service.embed([slice_.embedding_text for slice_ in pending])
            stamp = _now()
            with connect(self._path) as connection:
                for slice_, vector in zip(pending, vectors):
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO knowledge_vectors
                        (doc_id, slice_id, title, heading, content, doc_type, source,
                         updated_at, product_id, model, dim, embedding,
                         content_hash, indexed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            slice_.doc_id,
                            slice_.slice_id,
                            slice_.title,
                            slice_.heading,
                            slice_.content,
                            slice_.doc_type,
                            slice_.source,
                            slice_.updated_at,
                            slice_.product_id,
                            service.model,
                            service.dim,
                            json.dumps(vector),
                            content_hash(slice_),
                            stamp,
                        ),
                    )
                connection.commit()
            embedded = len(pending)
            if progress is not None:
                progress(embedded, len(pending))

        # 清理已不存在的切片
        current = {(slice_.doc_id, slice_.slice_id) for slice_ in slices}
        stale_ids = [key for key in existing if key not in current]
        if stale_ids:
            with connect(self._path) as connection:
                connection.executemany(
                    "DELETE FROM knowledge_vectors WHERE doc_id = ? AND slice_id = ?",
                    stale_ids,
                )
                connection.commit()

        # 索引变了就主动清缓存：不能等下一次 search 靠 mtime 猜。
        self._invalidate()
        logger.info(
            "向量索引完成：新增/更新 %d，跳过 %d，删除 %d",
            embedded,
            skipped,
            len(stale_ids),
        )
        return BuildResult(embedded=embedded, skipped=skipped, removed=len(stale_ids))

    # -- 概览 ------------------------------------------------------------

    def stats(self, slices: list[Slice], *, model: str, dim: int) -> IndexStats:
        rows = {(row["doc_id"], row["slice_id"]): row for row in self._rows()}
        ready = stale = missing = 0
        last = ""
        for slice_ in slices:
            row = rows.get((slice_.doc_id, slice_.slice_id))
            if row is None:
                missing += 1
                continue
            if (
                row["content_hash"] == content_hash(slice_)
                and row["model"] == model
                and int(row["dim"]) == dim
            ):
                ready += 1
                last = max(last, row["indexed_at"] or "")
            else:
                stale += 1
        return IndexStats(
            total_slices=len(slices),
            ready=ready,
            stale=stale,
            missing=missing,
            model=model,
            dim=dim,
            last_indexed_at=last,
        )

    def slice_rows(self, *, limit: int = 200) -> list[dict]:
        """给管理页用的切片状态表（已向量化的行）。"""
        rows = sorted(self._rows(), key=lambda r: (r["doc_id"], r["slice_id"]))
        return rows[:limit]

    # -- 检索 ------------------------------------------------------------

    def search(
        self,
        query_vector: list[float],
        *,
        model: str,
        dim: int,
        limit: int = 3,
        min_score: float | None = None,
    ) -> list[ScoredSlice]:
        """按余弦相似度取 top-k。只使用与当前模型/维度一致的行。

        边界输入（空向量、非一维、含 NaN/inf、全零、非正 limit）一律返回空列表
        而不抛异常：检索是问答链路的一环，不该因为一次异常输入让整页不可用。
        """
        if limit <= 0:
            logger.debug("检索 limit=%d，直接返回空结果", limit)
            return []
        if not query_vector:
            logger.debug("查询向量为空，直接返回空结果")
            return []
        try:
            query = np.asarray(query_vector, dtype=np.float32)
        except (TypeError, ValueError):
            logger.warning("查询向量无法转成数值数组，已跳过检索")
            return []
        if query.ndim != 1 or query.shape[0] == 0:
            logger.warning("查询向量维度非法：%s", query.shape)
            return []
        if not np.isfinite(query).all():
            logger.warning("查询向量含 NaN 或无穷大，已跳过检索")
            return []
        if not np.any(query):
            logger.debug("查询向量全零，余弦无意义，直接返回空结果")
            return []

        rows, matrix = self._matrix(model=model, dim=dim)
        if not rows:
            return []
        if matrix.shape[1] != query.shape[0]:
            logger.warning(
                "向量维度不一致：查询 %d，索引 %d —— 已忽略索引",
                query.shape[0],
                matrix.shape[1],
            )
            return []

        norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
        norms[norms == 0] = 1e-9
        scores = (matrix @ query) / norms

        threshold = config.KNOWLEDGE_MIN_COSINE if min_score is None else min_score
        order = np.argsort(-scores)

        hits: list[ScoredSlice] = []
        top_score = float(scores[order[0]]) if len(order) else 0.0
        if top_score < threshold:
            return []
        cutoff = max(threshold, top_score * config.KNOWLEDGE_RELATIVE_CUT)
        for index in order:
            score = float(scores[index])
            if score < cutoff or len(hits) >= limit:
                break
            row = rows[int(index)]
            hits.append(
                ScoredSlice(
                    slice=Slice(
                        slice_id=row["slice_id"],
                        doc_id=row["doc_id"],
                        title=row["title"],
                        heading=row["heading"],
                        content=row["content"],
                        doc_type=row["doc_type"],
                        source=row["source"],
                        updated_at=row["updated_at"],
                        product_id=row["product_id"],
                    ),
                    score=score,
                )
            )
        return hits
