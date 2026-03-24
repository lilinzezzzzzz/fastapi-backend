from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from pymilvus import DataType, FunctionType

from pkg.vectors.backends.base import CollectionSpec, ConsistencyLevel, FullTextSearchSpec
from pkg.vectors.backends.milvus import MilvusBackend
from pkg.vectors.backends.milvus.schema import build_schema
from pkg.vectors.contracts import RetrievalMode, SearchRequest, SearchReranker
from pkg.vectors.errors import CollectionSchemaMismatchError


async def _run_direct(func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.fixture(autouse=True)
def patch_run_in_thread():
    with patch("pkg.vectors.backends.milvus.backend.anyio_run_in_thread", new=_run_direct):
        yield


@pytest.fixture
def backend() -> MilvusBackend:
    return MilvusBackend(uri="http://test-milvus:19530")


@pytest.fixture
def collection_spec() -> CollectionSpec:
    return CollectionSpec(name="test_collection", dimension=4)


@pytest.fixture
def full_text_spec() -> CollectionSpec:
    return CollectionSpec(
        name="test_collection",
        dimension=4,
        full_text_search=FullTextSearchSpec(enabled=True),
    )


@pytest.fixture
def mock_client(backend: MilvusBackend) -> MagicMock:
    client = MagicMock()
    client.prepare_index_params.return_value = MagicMock()
    backend._client = client
    return client


def test_ensure_collection_uses_session_consistency(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = False

    asyncio.run(backend.ensure_collection(spec=collection_spec))

    assert mock_client.create_collection.call_args.kwargs["consistency_level"] == ConsistencyLevel.SESSION.value


def test_fetch_uses_session_consistency_by_default(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True
    mock_client.query.return_value = [
        {
            "id": 1,
            "text": "hello",
            "embedding": [0.1, 0.2, 0.3, 0.4],
        }
    ]

    asyncio.run(backend.fetch(spec=collection_spec, ids=[1]))

    assert mock_client.query.call_args.kwargs["consistency_level"] == ConsistencyLevel.SESSION.value


def test_fetch_allows_strong_consistency_override(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True
    mock_client.query.return_value = []

    asyncio.run(
        backend.fetch(
            spec=collection_spec,
            ids=[1],
            consistency_level=ConsistencyLevel.STRONG,
        )
    )

    assert mock_client.query.call_args.kwargs["consistency_level"] == ConsistencyLevel.STRONG.value


def test_fetch_requires_ids_or_filters(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True

    with pytest.raises(ValueError, match="fetch 需要至少提供 ids 或 filters"):
        asyncio.run(backend.fetch(spec=collection_spec))


def test_search_dense_uses_session_consistency_by_default(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True
    mock_client.search.return_value = [[{"id": 1, "distance": 0.01, "entity": {"text": "hello"}}]]

    asyncio.run(
        backend.search(
            spec=collection_spec,
            request=SearchRequest(vector=[0.1, 0.2, 0.3, 0.4], top_k=1),
        )
    )

    assert mock_client.search.call_args.kwargs["consistency_level"] == ConsistencyLevel.SESSION.value
    assert mock_client.search.call_args.kwargs["anns_field"] == collection_spec.vector_field


def test_search_auto_rejects_silent_dense_fallback_when_full_text_disabled(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True

    with pytest.raises(ValueError, match="AUTO 模式收到 vector \\+ query_text"):
        asyncio.run(
            backend.search(
                spec=collection_spec,
                request=SearchRequest(
                    vector=[0.1, 0.2, 0.3, 0.4],
                    query_text="hello",
                    top_k=2,
                ),
            )
        )


def test_search_hybrid_uses_rrf_reranker_by_default(
    backend: MilvusBackend,
    full_text_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True
    mock_client.hybrid_search.return_value = [[{"id": 1, "score": 0.8, "entity": {"text": "hello"}}]]

    asyncio.run(
        backend.search(
            spec=full_text_spec,
            request=SearchRequest(
                vector=[0.1, 0.2, 0.3, 0.4],
                query_text="hello",
                top_k=2,
            ),
        )
    )

    call_kwargs = mock_client.hybrid_search.call_args.kwargs
    assert call_kwargs["consistency_level"] == ConsistencyLevel.SESSION.value
    assert len(call_kwargs["reqs"]) == 2
    assert call_kwargs["reqs"][0]._anns_field == full_text_spec.vector_field
    assert call_kwargs["reqs"][1]._anns_field == full_text_spec.full_text_search.sparse_vector_field
    assert call_kwargs["ranker"].dict() == {"strategy": "rrf", "params": {"k": 60}}

    results = asyncio.run(
        backend.search(
            spec=full_text_spec,
            request=SearchRequest(
                vector=[0.1, 0.2, 0.3, 0.4],
                query_text="hello",
                top_k=2,
            ),
        )
    )
    assert results[0].retrieval_mode == RetrievalMode.HYBRID


def test_search_hybrid_supports_weighted_reranker(
    backend: MilvusBackend,
    full_text_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True
    mock_client.hybrid_search.return_value = [[]]

    asyncio.run(
        backend.search(
            spec=full_text_spec,
            request=SearchRequest(
                vector=[0.1, 0.2, 0.3, 0.4],
                query_text="hello",
                top_k=2,
                reranker=SearchReranker(strategy="weighted", weights=[0.7, 0.3]),
            ),
        )
    )

    assert mock_client.hybrid_search.call_args.kwargs["ranker"].dict() == {
        "strategy": "weighted",
        "params": {"weights": [0.7, 0.3], "norm_score": True},
    }


def test_search_full_text_only_uses_sparse_field(
    backend: MilvusBackend,
    full_text_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True
    mock_client.search.return_value = [[{"id": 1, "score": 4.2, "entity": {"text": "hello"}}]]

    asyncio.run(
        backend.search(
            spec=full_text_spec,
            request=SearchRequest(
                query_text="hello",
                top_k=2,
                retrieval_mode=RetrievalMode.FULL_TEXT,
            ),
        )
    )

    call_kwargs = mock_client.search.call_args.kwargs
    assert call_kwargs["anns_field"] == full_text_spec.full_text_search.sparse_vector_field
    assert call_kwargs["data"] == ["hello"]


def test_build_schema_adds_sparse_field_and_bm25_function(full_text_spec: CollectionSpec):
    schema = build_schema(spec=full_text_spec)

    sparse_field = next(
        field for field in schema.fields if field.name == full_text_spec.full_text_search.sparse_vector_field
    )
    assert sparse_field.dtype == DataType.SPARSE_FLOAT_VECTOR

    bm25_function = next(
        function for function in schema.functions if function.name == full_text_spec.full_text_search.function_name
    )
    assert bm25_function.type == FunctionType.BM25
    assert bm25_function.output_field_names == [full_text_spec.full_text_search.sparse_vector_field]


def test_ensure_collection_rejects_varchar_primary_key(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True
    mock_client.describe_collection.return_value = {
        "fields": [
            {"name": collection_spec.id_field, "type": "VarChar"},
            {"name": collection_spec.text_field, "type": "VarChar"},
            {"name": collection_spec.vector_field, "type": "FloatVector", "params": {"dim": collection_spec.dimension}},
            {"name": collection_spec.payload_field, "type": "JSON"},
        ]
    }

    with pytest.raises(CollectionSchemaMismatchError, match="主键字段类型不匹配"):
        asyncio.run(backend.ensure_collection(spec=collection_spec))
