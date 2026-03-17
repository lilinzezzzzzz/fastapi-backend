from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pkg.vector.backends.base import CollectionSpec
from pkg.vector.contracts import ConsistencyLevel, VectorRecord
from pkg.vector.repositories.base import BaseVectorRepository


class DummyRepository(BaseVectorRepository[str]):
    @property
    def collection_spec(self) -> CollectionSpec:
        return CollectionSpec(name="test_collection", dimension=4)

    def to_records(self, *, entity: str) -> list[VectorRecord]:
        return [
            VectorRecord(
                id=entity,
                text=entity,
                embedding=[0.1, 0.2, 0.3, 0.4],
            )
        ]


@pytest.fixture
def backend() -> MagicMock:
    backend = MagicMock()
    backend.ensure_collection = AsyncMock()
    backend.upsert = AsyncMock()
    backend.delete = AsyncMock(return_value=0)
    backend.fetch = AsyncMock(return_value=[])
    backend.search = AsyncMock(return_value=[])
    return backend


@pytest.fixture
def embedder() -> MagicMock:
    embedder = MagicMock()
    embedder.embed_query = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])
    embedder.embed_texts = AsyncMock(return_value=[])
    return embedder


def test_fetch_by_ids_passes_consistency_level(backend: MagicMock, embedder: MagicMock):
    repo = DummyRepository(backend=backend, embedder=embedder)

    asyncio.run(
        repo.fetch_by_ids(
            ids=["doc-1"],
            consistency_level=ConsistencyLevel.STRONG,
        )
    )

    assert backend.fetch.await_args.kwargs["consistency_level"] == ConsistencyLevel.STRONG


def test_search_by_text_passes_consistency_level(backend: MagicMock, embedder: MagicMock):
    repo = DummyRepository(backend=backend, embedder=embedder)

    asyncio.run(
        repo.search_by_text(
            query_text="hello",
            top_k=1,
            consistency_level=ConsistencyLevel.STRONG,
        )
    )

    request = backend.search.await_args.kwargs["request"]
    assert request.consistency_level == ConsistencyLevel.STRONG
