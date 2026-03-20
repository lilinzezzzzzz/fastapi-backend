from __future__ import annotations

import contextlib
import threading
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

import anyio
import grpc
from pymilvus import MilvusClient
from pymilvus.exceptions import (
    ConnectError,
    ConnectionNotExistException,
    MilvusUnavailableException,
)

from pkg.toolkit.async_task import anyio_run_in_thread
from pkg.vectors.backends.base import BaseVectorBackend, CollectionSpec
from pkg.vectors.contracts import (
    FilterCondition,
    SearchHit,
    SearchRequest,
    VectorRecord,
)

from .query import (
    build_fetch_output_fields,
    build_filter_expression,
    build_search_output_fields,
    hit_to_search_hit,
    record_to_row,
    row_to_record,
)
from .schema import (
    build_index_params,
    build_schema,
    map_metric_type,
    validate_collection_description,
)

T = TypeVar("T")


class MilvusBackend(BaseVectorBackend):
    """基于 pymilvus.MilvusClient 的 clean backend。"""

    def __init__(
        self,
        *,
        uri: str,
        token: str | None = None,
        db_name: str | None = None,
        timeout: float | None = None,
        default_search_params: dict[str, object] | None = None,
    ) -> None:
        self._uri = uri
        self._token = token or ""
        self._db_name = db_name or ""
        self._timeout = timeout
        self._default_search_params = default_search_params or {}
        self._client: MilvusClient | None = None
        self._client_guard = threading.Lock()
        self._recovery_lock = anyio.Lock()
        self._collection_locks: dict[str, anyio.Lock] = {}
        self._loaded_collections: set[str] = set()
        self._ensured_collections: set[str] = set()
        self._is_shutdown = False

    @property
    def client(self) -> MilvusClient:
        if self._client is not None:
            return self._client

        if self._is_shutdown:
            raise RuntimeError("Milvus backend is shut down")

        with self._client_guard:
            if self._client is None:
                if self._is_shutdown:
                    raise RuntimeError("Milvus backend is shut down")
                self._client = MilvusClient(
                    uri=self._uri,
                    token=self._token,
                    db_name=self._db_name,
                    timeout=self._timeout,
                )
            return self._client

    def close(self) -> None:
        self._close_client(reset_only=True)

    def shutdown(self) -> None:
        self._close_client(reset_only=False)

    def _close_client(self, *, reset_only: bool) -> None:
        with self._client_guard:
            client = self._client
            self._client = None
            if not reset_only:
                self._is_shutdown = True
            self._loaded_collections.clear()
            self._ensured_collections.clear()

        if client is not None:
            with contextlib.suppress(Exception):
                client.close()

    async def _call_client(
        self,
        operation: Callable[[MilvusClient], T],
    ) -> T:
        def _run_operation() -> T:
            return operation(self.client)

        return await anyio_run_in_thread(_run_operation)

    async def _call_client_method(self, method_name: str, /, **kwargs: object) -> T:
        def _run_method(client: MilvusClient) -> T:
            method = getattr(client, method_name)
            return method(**kwargs)

        return await self._call_client(_run_method)

    async def _run_with_recovery(self, operation: Callable[[], Awaitable[T]]) -> T:
        try:
            return await operation()
        except Exception as exc:
            if not self._is_recoverable_client_error(exc):
                raise
            await self._reset_client_state()
            return await operation()

    async def _reset_client_state(self, *, stale_client: MilvusClient | None = None) -> None:
        async with self._recovery_lock:
            client = self._client
            if stale_client is not None and client is not stale_client:
                return

            self._client = None
            self._loaded_collections.clear()
            self._ensured_collections.clear()

            if client is None:
                return

            with contextlib.suppress(Exception):
                await anyio_run_in_thread(client.close)

    @staticmethod
    def _is_recoverable_client_error(exc: Exception) -> bool:
        if isinstance(
            exc,
            (ConnectError, ConnectionNotExistException, MilvusUnavailableException),
        ):
            return True
        if isinstance(exc, grpc.RpcError):
            return exc.code() in {
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.DEADLINE_EXCEEDED,
                grpc.StatusCode.CANCELLED,
            }
        return False

    async def ensure_collection(self, *, spec: CollectionSpec) -> None:
        async def _run() -> None:
            if spec.name in self._ensured_collections:
                return

            async with self._get_collection_lock(collection_name=spec.name):
                if spec.name in self._ensured_collections:
                    return

                exists = spec.name in self._loaded_collections
                if not exists:
                    exists = await self._call_client_method(
                        "has_collection",
                        collection_name=spec.name,
                    )

                if exists:
                    await self._validate_existing_collection(spec=spec)
                    await self._load_collection_if_needed(collection_name=spec.name)
                else:
                    schema = build_schema(spec=spec)
                    index_params = build_index_params(client=self.client, spec=spec)
                    await self._call_client_method(
                        "create_collection",
                        collection_name=spec.name,
                        schema=schema,
                        index_params=index_params,
                        consistency_level=spec.consistency_level.value,
                    )
                    await self._load_collection_if_needed(collection_name=spec.name)

                self._ensured_collections.add(spec.name)

        await self._run_with_recovery(_run)

    async def load_collection(self, *, collection_name: str) -> None:
        async def _run() -> None:
            async with self._get_collection_lock(collection_name=collection_name):
                await self._load_collection_if_needed(collection_name=collection_name)

        await self._run_with_recovery(_run)

    async def upsert(
        self, *, spec: CollectionSpec, records: Sequence[VectorRecord]
    ) -> None:
        async def _run() -> None:
            if not records:
                return

            self.validate_records(spec=spec, records=records)
            await self.ensure_collection(spec=spec)
            rows = [record_to_row(spec=spec, record=record) for record in records]
            await self._call_client_method(
                "upsert",
                collection_name=spec.name,
                data=rows,
            )

        await self._run_with_recovery(_run)

    async def delete(
        self,
        *,
        spec: CollectionSpec,
        ids: Sequence[int] | None = None,
        filters: Sequence[FilterCondition] | None = None,
    ) -> int:
        async def _run() -> int:
            if not await self._collection_exists(collection_name=spec.name):
                return 0

            expr = build_filter_expression(spec=spec, ids=ids, filters=filters)
            if ids is not None and len(ids) > 0 and not filters:
                result = await self._call_client_method(
                    "delete",
                    collection_name=spec.name,
                    ids=list(ids),
                )
            elif expr:
                result = await self._call_client_method(
                    "delete",
                    collection_name=spec.name,
                    filter=expr,
                )
            else:
                return 0

            return int(result.get("delete_count", 0))

        return await self._run_with_recovery(_run)

    async def fetch(
        self,
        *,
        spec: CollectionSpec,
        ids: Sequence[int] | None = None,
        filters: Sequence[FilterCondition] | None = None,
        limit: int | None = None,
    ) -> list[VectorRecord]:
        async def _run() -> list[VectorRecord]:
            if not await self._load_collection_if_exists(collection_name=spec.name):
                return []

            output_fields = build_fetch_output_fields(spec=spec)
            expr = build_filter_expression(spec=spec, ids=ids, filters=filters)
            if ids is not None and len(ids) > 0 and not filters:
                rows = await self._call_client_method(
                    "query",
                    collection_name=spec.name,
                    ids=list(ids),
                    output_fields=output_fields,
                )
            else:
                rows = await self._call_client_method(
                    "query",
                    collection_name=spec.name,
                    filter=expr,
                    output_fields=output_fields,
                )

            records = [row_to_record(spec=spec, row=row) for row in rows]
            return records[:limit] if limit is not None else records

        return await self._run_with_recovery(_run)

    async def search(
        self, *, spec: CollectionSpec, request: SearchRequest
    ) -> list[SearchHit]:
        async def _run() -> list[SearchHit]:
            self.validate_search_request(spec=spec, request=request)
            if not await self._load_collection_if_exists(collection_name=spec.name):
                return []

            expr = build_filter_expression(
                spec=spec,
                ids=None,
                filters=request.filters,
            )
            output_fields = build_search_output_fields(spec=spec, request=request)
            search_params = self._build_search_params(spec=spec, request=request)
            raw_results = await self._call_client_method(
                "search",
                collection_name=spec.name,
                data=[request.vector],
                filter=expr,
                limit=request.top_k,
                output_fields=output_fields,
                search_params=search_params,
                anns_field=spec.vector_field,
            )
            hits = raw_results[0] if raw_results else []
            return [hit_to_search_hit(spec=spec, hit=hit) for hit in hits]

        return await self._run_with_recovery(_run)

    async def healthcheck(self) -> dict[str, str]:
        async def _run() -> dict[str, str]:
            version = await self._call_client_method("get_server_version")
            return {
                "backend": "milvus",
                "status": "ok",
                "version": str(version),
            }

        return await self._run_with_recovery(_run)

    async def release_collection(self, *, collection_name: str) -> None:
        async def _run() -> None:
            async with self._get_collection_lock(collection_name=collection_name):
                await self._call_client_method(
                    "release_collection",
                    collection_name=collection_name,
                )
                self._loaded_collections.discard(collection_name)
                self._ensured_collections.discard(collection_name)

        await self._run_with_recovery(_run)

    async def _load_collection_if_exists(self, *, collection_name: str) -> bool:
        if collection_name in self._loaded_collections:
            return True

        async with self._get_collection_lock(collection_name=collection_name):
            if collection_name in self._loaded_collections:
                return True

            exists = await self._collection_exists(collection_name=collection_name)
            if not exists:
                return False

            await self._load_collection_if_needed(collection_name=collection_name)
            return True

    def _get_collection_lock(self, *, collection_name: str) -> anyio.Lock:
        lock = self._collection_locks.get(collection_name)
        if lock is None:
            lock = anyio.Lock()
            self._collection_locks[collection_name] = lock
        return lock

    async def _load_collection_if_needed(self, *, collection_name: str) -> None:
        if collection_name in self._loaded_collections:
            return

        await self._call_client_method(
            "load_collection",
            collection_name=collection_name,
        )
        self._loaded_collections.add(collection_name)

    async def _collection_exists(self, *, collection_name: str) -> bool:
        if collection_name in self._loaded_collections:
            return True

        return bool(
            await self._call_client_method(
                "has_collection",
                collection_name=collection_name,
            )
        )

    async def _validate_existing_collection(self, *, spec: CollectionSpec) -> None:
        description = await self._call_client_method(
            "describe_collection",
            collection_name=spec.name,
        )
        validate_collection_description(description=description, spec=spec)

    def _build_search_params(
        self,
        *,
        spec: CollectionSpec,
        request: SearchRequest,
    ) -> dict[str, object]:
        search_params = dict(self._default_search_params)
        if "metric_type" not in search_params:
            search_params["metric_type"] = map_metric_type(spec.metric_type)
        if "params" not in search_params:
            search_params["params"] = {}
        search_params.update(request.search_params)
        return search_params
