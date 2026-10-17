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
        """按余弦相似度取 top-k。只使用与当前模型/维度一致的行。"""
        rows = [
            row
            for row in self._rows()
            if row["model"] == model and int(row["dim"]) == dim
        ]
        if not rows:
            return []

        query = np.asarray(query_vector, dtype=np.float32)
        matrix = np.asarray([json.loads(row["embedding"]) for row in rows], dtype=np.float32)
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
