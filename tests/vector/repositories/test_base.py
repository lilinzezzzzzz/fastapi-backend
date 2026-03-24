from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pkg.vectors.backends.base import CollectionSpec
from pkg.vectors.context_assembly import DocumentContextAssembler
from pkg.vectors.contracts import ConsistencyLevel, RetrievalMode, SearchHit, VectorRecord
from pkg.vectors.post_retrieval import PostRetrievalPipeline
from pkg.vectors.repositories.base import BaseVectorRepository


class DummyRepository(BaseVectorRepository[int]):
    @property
    def collection_spec(self) -> CollectionSpec:
        return CollectionSpec(name="test_collection", dimension=4)

    def to_records(self, *, entity: int) -> list[VectorRecord]:
        return [
            VectorRecord(
                id=entity,
                text=str(entity),
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
            ids=[1],
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
    assert request.query_text == "hello"


def test_search_by_text_full_text_mode_skips_embedding(
    backend: MagicMock,
    embedder: MagicMock,
):
    repo = DummyRepository(backend=backend, embedder=embedder)

    asyncio.run(
        repo.search_by_text(
            query_text="hello",
            top_k=1,
            retrieval_mode=RetrievalMode.FULL_TEXT,
        )
    )

    embedder.embed_query.assert_not_awaited()
    request = backend.search.await_args.kwargs["request"]
    assert request.vector is None
    assert request.retrieval_mode == RetrievalMode.FULL_TEXT


def test_retrieve_by_text_runs_post_retrieval_pipeline(
    backend: MagicMock,
    embedder: MagicMock,
):
    repo = DummyRepository(backend=backend, embedder=embedder)
    backend.search.return_value = [
        SearchHit(id=1, text="chunk-1", metadata={"doc_id": 10}, relevance_score=0.9),
        SearchHit(id=2, text="chunk-2", metadata={"doc_id": 10}, relevance_score=0.8),
        SearchHit(id=3, text="chunk-3", metadata={"doc_id": 20}, relevance_score=0.85),
    ]

    result = asyncio.run(
        repo.retrieve_by_text(
            query_text="hello",
            top_k=3,
            post_retrieval=PostRetrievalPipeline(),
        )
    )

    assert result.stats.input_hit_count == 3
    assert len(result.documents) == 2
    assert result.documents[0].document_key == 10


def test_assemble_context_by_text_runs_post_retrieval_and_context_assembly(
    backend: MagicMock,
    embedder: MagicMock,
):
    repo = DummyRepository(backend=backend, embedder=embedder)
    backend.search.return_value = [
        SearchHit(
            id=2,
            text="chunk-2",
            metadata={"doc_id": 10, "chunk_index": 2, "title": "Doc 10"},
            relevance_score=0.9,
        ),
        SearchHit(
            id=1,
            text="chunk-1",
            metadata={"doc_id": 10, "chunk_index": 1, "title": "Doc 10"},
            relevance_score=0.95,
        ),
        SearchHit(
            id=3,
            text="chunk-3",
            metadata={"doc_id": 20, "chunk_index": 1, "title": "Doc 20"},
            relevance_score=0.85,
        ),
    ]

    result = asyncio.run(
        repo.assemble_context_by_text(
            query_text="hello",
            top_k=3,
            post_retrieval=PostRetrievalPipeline(),
            context_assembler=DocumentContextAssembler(),
        )
    )

    assert len(result.documents) == 2
    assert result.documents[0].document_key == 10
    assert result.documents[0].chunk_ids == [1, 2]
    assert "Doc 10" in result.context_text
    assert result.context_text.index("chunk-1") < result.context_text.index("chunk-2")
