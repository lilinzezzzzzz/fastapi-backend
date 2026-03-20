from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from pymilvus import DataType

from pkg.vectors.backends.base import CollectionSpec, ConsistencyLevel
from pkg.vectors.backends.milvus import MilvusBackend
from pkg.vectors.contracts import SearchRequest
from pkg.vectors.errors import CollectionSchemaMismatchError


async def _run_direct(func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.fixture(autouse=True)
def patch_run_in_thread():
    with patch("pkg.vector.backends.milvus.anyio_run_in_thread", new=_run_direct):
        yield


@pytest.fixture
def backend() -> MilvusBackend:
    return MilvusBackend(uri="http://test-milvus:19530")


@pytest.fixture
def collection_spec() -> CollectionSpec:
    return CollectionSpec(name="test_collection", dimension=4)


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


def test_delete_does_not_flush(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.delete.return_value = {"delete_count": 1}

    deleted = asyncio.run(backend.delete(spec=collection_spec, ids=[1]))

    assert deleted == 1
    mock_client.flush.assert_not_called()


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


def test_search_uses_session_consistency_by_default(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True
    mock_client.search.return_value = [
        [
            {
                "id": 1,
                "distance": 0.01,
                "entity": {"text": "hello"},
            }
        ]
    ]

    asyncio.run(
        backend.search(
            spec=collection_spec,
            request=SearchRequest(vector=[0.1, 0.2, 0.3, 0.4], top_k=1),
        )
    )

    assert mock_client.search.call_args.kwargs["consistency_level"] == ConsistencyLevel.SESSION.value


def test_search_allows_strong_consistency_override(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
    mock_client: MagicMock,
):
    mock_client.has_collection.return_value = True
    mock_client.search.return_value = [[]]

    asyncio.run(
        backend.search(
            spec=collection_spec,
            request=SearchRequest(
                vector=[0.1, 0.2, 0.3, 0.4],
                top_k=1,
                consistency_level=ConsistencyLevel.STRONG,
            ),
        )
    )

    assert mock_client.search.call_args.kwargs["consistency_level"] == ConsistencyLevel.STRONG.value


def test_build_schema_uses_int64_primary_key(
    backend: MilvusBackend,
    collection_spec: CollectionSpec,
):
    schema = backend._build_schema(spec=collection_spec)

    primary_field = next(field for field in schema.fields if field.name == collection_spec.id_field)
    assert primary_field.dtype == DataType.INT64


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
