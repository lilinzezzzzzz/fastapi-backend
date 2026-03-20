from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import StrEnum

from pkg.vectors.errors import InvalidEmbeddingDimensionError


class EmbedderProvider(StrEnum):
    LLM = "llm"


class Embedder(ABC):
    @abstractmethod
    async def embed_texts(self, *, texts: Sequence[str], dimension: int | None = None) -> list[list[float]]:
        """批量文本向量化。"""

    @abstractmethod
    async def embed_text(self, *, text: str, dimension: int | None = None) -> list[float]:
        """单个文本向量化。"""

    async def embed_query(self, *, text: str, dimension: int | None = None) -> list[float]:
        """查询文本向量化（默认调用 embed_text）。"""
        return await self.embed_text(text=text, dimension=dimension)

    async def embed_text_safe(
        self,
        *,
        text: str,
        dimension: int | None = None,
        caller_module: str = "embed_text_safe",
    ) -> list[float]:
        """单个文本向量化（带异常捕获，默认调用 embed_text）。"""
        return await self.embed_text(text=text, dimension=dimension)


class BaseEmbedder(Embedder):
    def __init__(self, *, dimension: int | None = None) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int | None:
        return self._dimension

    def validate_vector(self, vector: Sequence[float], *, source: str) -> None:
        if self._dimension is None:
            return
        if len(vector) != self._dimension:
            raise InvalidEmbeddingDimensionError(f"{source} 维度不匹配: got={len(vector)}, expected={self._dimension}")

    def validate_vectors(self, vectors: Sequence[Sequence[float]], *, source: str) -> None:
        for index, vector in enumerate(vectors):
            self.validate_vector(vector, source=f"{source}[{index}]")
