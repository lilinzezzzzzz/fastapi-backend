from __future__ import annotations

import asyncio
import contextlib
import os
import uuid

import pytest

from pkg.vectors.backends.base import ScalarDataType, ScalarFieldSpec
from pkg.vectors.backends.milvus import MilvusBackend
from pkg.vectors.backends.milvus.specs import FullTextSearchSpec, MilvusCollectionSpec
from pkg.vectors.contracts import (
    ConsistencyLevel,
    FilterCondition,
    FilterOperator,
    RetrievalMode,
    SearchRequest,
    VectorRecord,
)

TEST_MILVUS_URI = os.getenv("TEST_MILVUS_URI", "http://localhost:19530")


@pytest.fixture
def backend() -> MilvusBackend:
    return MilvusBackend(uri=TEST_MILVUS_URI, timeout=10.0)


@pytest.fixture
def collection_spec() -> MilvusCollectionSpec:
    collection_name = f"test_milvus_backend_{uuid.uuid4().hex[:8]}"
    return MilvusCollectionSpec(
        name=collection_name,
        dimension=4,
        scalar_fields=[
            ScalarFieldSpec(name="tenant_id", data_type=ScalarDataType.INT64),
            ScalarFieldSpec(name="doc_id", data_type=ScalarDataType.INT64),
        ],
        full_text_search=FullTextSearchSpec(enabled=True),
    )


@pytest.fixture(autouse=True)
def cleanup_collection(backend: MilvusBackend, collection_spec: MilvusCollectionSpec):
    yield
    with contextlib.suppress(Exception):
        backend.client.drop_collection(collection_name=collection_spec.name)
    backend.close()


async def _wait_for_hits(
    backend: MilvusBackend,
    spec: MilvusCollectionSpec,
    request: SearchRequest,
) -> list:
    for _ in range(10):
        hits = await backend.search(spec=spec, request=request)
        if hits:
            return hits
        await asyncio.sleep(0.5)
    return []


@pytest.mark.integration
async def test_milvus_full_text_and_hybrid_search_work(
    backend: MilvusBackend,
    collection_spec: MilvusCollectionSpec,
):
    await backend.ensure_collection(spec=collection_spec)
    await backend.upsert(
        spec=collection_spec,
        records=[
            VectorRecord(
                id=1,
                text="Milvus hybrid retrieval combines dense search and BM25",
                embedding=[1.0, 0.0, 0.0, 0.0],
                metadata={"tenant_id": 1, "doc_id": 101},
            ),
            VectorRecord(
                id=2,
                text="ConnectionNotExistException usually indicates broken client state",
                embedding=[0.0, 1.0, 0.0, 0.0],
                metadata={"tenant_id": 1, "doc_id": 102},
            ),
            VectorRecord(
                id=3,
                text="A different document about ranking signals",
                embedding=[0.0, 0.0, 1.0, 0.0],
                metadata={"tenant_id": 2, "doc_id": 103},
            ),
        ],
    )

    full_text_hits = await _wait_for_hits(
        backend,
        collection_spec,
        SearchRequest(
            query_text="ConnectionNotExistException",
            top_k=2,
            retrieval_mode=RetrievalMode.FULL_TEXT,
            consistency_level=ConsistencyLevel.STRONG,
        ),
    )
    assert full_text_hits
    assert full_text_hits[0].id == 2
    assert full_text_hits[0].retrieval_mode == RetrievalMode.FULL_TEXT

    hybrid_hits = await _wait_for_hits(
        backend,
        collection_spec,
        SearchRequest(
            vector=[1.0, 0.0, 0.0, 0.0],
            query_text="hybrid retrieval dense BM25",
            top_k=2,
            candidate_top_k=3,
            consistency_level=ConsistencyLevel.STRONG,
        ),
    )
    assert hybrid_hits
    assert hybrid_hits[0].id == 1
    assert hybrid_hits[0].retrieval_mode == RetrievalMode.HYBRID


@pytest.mark.integration
async def test_milvus_fetch_limit_and_fail_fast(
    backend: MilvusBackend,
    collection_spec: MilvusCollectionSpec,
):
    await backend.ensure_collection(spec=collection_spec)
    await backend.upsert(
        spec=collection_spec,
        records=[
            VectorRecord(
                id=11,
                text="doc one",
                embedding=[1.0, 0.0, 0.0, 0.0],
                metadata={"tenant_id": 9, "doc_id": 201},
            ),
            VectorRecord(
                id=12,
                text="doc two",
                embedding=[0.0, 1.0, 0.0, 0.0],
                metadata={"tenant_id": 9, "doc_id": 202},
            ),
        ],
    )

    with pytest.raises(ValueError, match="fetch 需要至少提供 ids 或 filters"):
        await backend.fetch(spec=collection_spec)

    records = await backend.fetch(
        spec=collection_spec,
        filters=[FilterCondition(field="tenant_id", op=FilterOperator.EQ, value=9)],
        limit=1,
        consistency_level=ConsistencyLevel.STRONG,
    )
    assert len(records) == 1
