from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pymilvus import DataType, MilvusClient

from pkg.toolkit.async_task import anyio_run_in_thread
from pkg.vector.backends.base import (
    BaseVectorBackend,
    CollectionSpec,
    ConsistencyLevel,
    MetricType,
    ScalarDataType,
    VectorBackend,
    scalar_field_names,
)
from pkg.vector.contracts import (
    FilterCondition,
    FilterOperator,
    SearchHit,
    SearchRequest,
    VectorRecord,
)
from pkg.vector.errors import CollectionSchemaMismatchError, UnsupportedFilterError


class MilvusBackend(BaseVectorBackend):
    """基于 pymilvus.MilvusClient 的 clean backend。"""

    def __init__(
        self,
        *,
        uri: str,
        token: str | None = None,
        db_name: str | None = None,
        timeout: float | None = None,
        default_search_params: dict[str, Any] | None = None,
    ) -> None:
        self._uri = uri
        self._token = token or ""
        self._db_name = db_name or ""
        self._timeout = timeout
        self._default_search_params = default_search_params or {}
        self._client: MilvusClient | None = None

    @property
    def client(self) -> MilvusClient:
        if self._client is None:
            self._client = MilvusClient(
                uri=self._uri,
                token=self._token,
                db_name=self._db_name,
                timeout=self._timeout,
            )
        return self._client

    async def ensure_collection(self, *, spec: CollectionSpec) -> None:
        exists = await anyio_run_in_thread(
            self.client.has_collection,
            collection_name=spec.name,
        )
        if exists:
            await self._validate_existing_collection(spec=spec)
            await self.load_collection(collection_name=spec.name)
            return

        schema = self._build_schema(spec=spec)
        index_params = self._build_index_params(spec=spec)
        await anyio_run_in_thread(
            self.client.create_collection,
            collection_name=spec.name,
            schema=schema,
            index_params=index_params,
            consistency_level=self._resolve_consistency_level(spec.consistency_level),
        )
        await self.load_collection(collection_name=spec.name)

    async def upsert(self, *, spec: CollectionSpec, records: Sequence[VectorRecord]) -> None:
        if not records:
            return

        self.validate_records(spec=spec, records=records)
        rows = [self._record_to_row(spec=spec, record=record) for record in records]
        await anyio_run_in_thread(
            self.client.upsert,
            collection_name=spec.name,
            data=rows,
        )

    async def delete(
        self,
        *,
        spec: CollectionSpec,
        ids: Sequence[str] | None = None,
        filters: Sequence[FilterCondition] | None = None,
    ) -> int:
        expr = self._build_filter_expression(spec=spec, ids=ids, filters=filters)
        if ids and not filters:
            result = await anyio_run_in_thread(
                self.client.delete,
                collection_name=spec.name,
                ids=list(ids),
            )
        elif expr:
            result = await anyio_run_in_thread(
                self.client.delete,
                collection_name=spec.name,
                filter=expr,
            )
        else:
            return 0
        return int(result.get("delete_count", 0))

    async def fetch(
        self,
        *,
        spec: CollectionSpec,
        ids: Sequence[str] | None = None,
        filters: Sequence[FilterCondition] | None = None,
        limit: int | None = None,
        consistency_level: ConsistencyLevel | None = None,
    ) -> list[VectorRecord]:
        if not await self._ensure_collection_loaded_if_exists(collection_name=spec.name):
            return []

        output_fields = self._build_fetch_output_fields(spec=spec)
        expr = self._build_filter_expression(spec=spec, ids=ids, filters=filters)
        resolved_consistency_level = self._resolve_consistency_level(
            consistency_level or spec.consistency_level
        )
        if ids and not filters:
            rows = await anyio_run_in_thread(
                self.client.query,
                collection_name=spec.name,
                ids=list(ids),
                output_fields=output_fields,
                consistency_level=resolved_consistency_level,
            )
        else:
            rows = await anyio_run_in_thread(
                self.client.query,
                collection_name=spec.name,
                filter=expr,
                output_fields=output_fields,
                consistency_level=resolved_consistency_level,
            )

        records = [self._row_to_record(spec=spec, row=row) for row in rows]
        return records[:limit] if limit is not None else records

    async def search(self, *, spec: CollectionSpec, request: SearchRequest) -> list[SearchHit]:
        self.validate_search_request(spec=spec, request=request)
        if not await self._ensure_collection_loaded_if_exists(collection_name=spec.name):
            return []
        expr = self._build_filter_expression(
            spec=spec,
            ids=None,
            filters=request.filters,
        )
        output_fields = self._build_search_output_fields(spec=spec, request=request)
        search_params = self._build_search_params(spec=spec, request=request)
        resolved_consistency_level = self._resolve_consistency_level(
            request.consistency_level or spec.consistency_level
        )
        raw_results = await anyio_run_in_thread(
            self.client.search,
            collection_name=spec.name,
            data=[request.vector],
            filter=expr,
            limit=request.top_k,
            output_fields=output_fields,
            search_params=search_params,
            anns_field=spec.vector_field,
            consistency_level=resolved_consistency_level,
        )
        hits = raw_results[0] if raw_results else []
        return [self._hit_to_search_hit(spec=spec, hit=hit) for hit in hits]

    async def healthcheck(self) -> dict[str, str]:
        version = await anyio_run_in_thread(self.client.get_server_version)
        return {
            "backend": "milvus",
            "status": "ok",
            "version": str(version),
        }

    async def load_collection(self, *, collection_name: str) -> None:
        await anyio_run_in_thread(
            self.client.load_collection,
            collection_name=collection_name,
        )

    async def release_collection(self, *, collection_name: str) -> None:
        await anyio_run_in_thread(
            self.client.release_collection,
            collection_name=collection_name,
        )

    async def _ensure_collection_loaded_if_exists(self, *, collection_name: str) -> bool:
        exists = await anyio_run_in_thread(
            self.client.has_collection,
            collection_name=collection_name,
        )
        if not exists:
            return False

        await self.load_collection(collection_name=collection_name)
        return True

    async def _validate_existing_collection(self, *, spec: CollectionSpec) -> None:
        description = await anyio_run_in_thread(
            self.client.describe_collection,
            collection_name=spec.name,
        )
        if not isinstance(description, dict):
            return

        fields = description.get("fields")
        if not isinstance(fields, list):
            return

        field_map: dict[str, dict[str, Any]] = {}
        for field in fields:
            if isinstance(field, dict) and isinstance(field.get("name"), str):
                field_map[field["name"]] = field

        for required_field in [spec.id_field, spec.text_field, spec.vector_field]:
            if required_field not in field_map:
                raise CollectionSchemaMismatchError(
                    f"Milvus collection 字段缺失: collection={spec.name}, field={required_field}"
                )

        if spec.payload_field and spec.payload_field not in field_map:
            raise CollectionSchemaMismatchError(
                f"Milvus collection 缺少 payload 字段: collection={spec.name}, field={spec.payload_field}"
            )

        for scalar_field in spec.scalar_fields:
            if scalar_field.name not in field_map:
                raise CollectionSchemaMismatchError(
                    f"Milvus collection 缺少 metadata 字段: collection={spec.name}, field={scalar_field.name}"
                )

        vector_field = field_map.get(spec.vector_field, {})
        params = vector_field.get("params")
        if isinstance(params, dict) and "dim" in params:
            dimension = int(params["dim"])
            if dimension != spec.dimension:
                raise CollectionSchemaMismatchError(
                    f"Milvus vector dim 不匹配: collection={spec.name}, got={dimension}, expected={spec.dimension}"
                )

    def _build_schema(self, *, spec: CollectionSpec):
        schema = MilvusClient.create_schema(
            auto_id=False,
            enable_dynamic_field=spec.enable_dynamic_field,
        )
        schema.add_field(
            field_name=spec.id_field,
            datatype=DataType.VARCHAR,
            is_primary=True,
            max_length=spec.id_max_length,
        )
        schema.add_field(
            field_name=spec.text_field,
            datatype=DataType.VARCHAR,
            max_length=spec.text_max_length,
        )
        schema.add_field(
            field_name=spec.vector_field,
            datatype=DataType.FLOAT_VECTOR,
            dim=spec.dimension,
        )

        if spec.payload_field:
            schema.add_field(
                field_name=spec.payload_field,
                datatype=DataType.JSON,
                nullable=True,
            )

        for field in spec.scalar_fields:
            kwargs: dict[str, Any] = {"nullable": field.nullable}
            if field.data_type == ScalarDataType.STRING:
                kwargs["max_length"] = field.max_length or 512
            schema.add_field(
                field_name=field.name,
                datatype=self._map_data_type(field.data_type),
                **kwargs,
            )

        return schema

    def _build_index_params(self, *, spec: CollectionSpec):
        index_params = self.client.prepare_index_params()
        index_config = dict(spec.index_config)
        vector_index_params = dict(index_config.pop("params", {}))
        index_params.add_index(
            field_name=spec.vector_field,
            index_name=index_config.pop("index_name", f"idx_{spec.vector_field}"),
            index_type=index_config.pop("index_type", "AUTOINDEX"),
            metric_type=index_config.pop("metric_type", self._map_metric_type(spec.metric_type)),
            params=vector_index_params,
            **index_config,
        )
        return index_params

    def _build_search_params(self, *, spec: CollectionSpec, request: SearchRequest) -> dict[str, Any]:
        search_params = dict(self._default_search_params)
        if "metric_type" not in search_params:
            search_params["metric_type"] = self._map_metric_type(spec.metric_type)
        if "params" not in search_params:
            search_params["params"] = {}
        search_params.update(request.search_params)
        return search_params

    @staticmethod
    def _resolve_consistency_level(consistency_level: ConsistencyLevel) -> str:
        return str(consistency_level.value)

    def _record_to_row(self, *, spec: CollectionSpec, record: VectorRecord) -> dict[str, Any]:
        row: dict[str, Any] = {
            spec.id_field: record.id,
            spec.text_field: record.text,
            spec.vector_field: record.embedding,
        }
        if spec.payload_field:
            row[spec.payload_field] = record.payload
        row.update(record.metadata)
        return row

    def _row_to_record(self, *, spec: CollectionSpec, row: dict[str, Any]) -> VectorRecord:
        metadata = {field.name: row[field.name] for field in spec.scalar_fields if field.name in row}
        payload = {}
        if spec.payload_field:
            payload_value = row.get(spec.payload_field)
            if isinstance(payload_value, dict):
                payload = payload_value

        embedding = row.get(spec.vector_field)
        return VectorRecord(
            id=str(row.get(spec.id_field)),
            text=str(row.get(spec.text_field, "")),
            embedding=embedding if isinstance(embedding, list) else None,
            metadata=metadata,
            payload=payload,
        )

    def _hit_to_search_hit(self, *, spec: CollectionSpec, hit: dict[str, Any]) -> SearchHit:
        row = self._extract_entity_row(spec=spec, hit=hit)
        raw_score = self._extract_raw_score(hit=hit)
        return SearchHit(
            id=str(hit.get("id", row.get(spec.id_field, ""))),
            text=row.get(spec.text_field),
            metadata={field.name: row[field.name] for field in spec.scalar_fields if field.name in row},
            payload=self._extract_payload(spec=spec, row=row),
            relevance_score=self._normalize_score(
                metric_type=spec.metric_type,
                raw_score=raw_score,
            ),
            raw_score=raw_score,
        )

    def _extract_entity_row(self, *, spec: CollectionSpec, hit: dict[str, Any]) -> dict[str, Any]:
        entity = hit.get("entity")
        if isinstance(entity, dict):
            return dict(entity)

        row = {key: value for key, value in hit.items() if key not in {"id", "distance", "score", "entity"}}
        if spec.id_field not in row and "id" in hit:
            row[spec.id_field] = hit["id"]
        return row

    def _extract_payload(self, *, spec: CollectionSpec, row: dict[str, Any]) -> dict[str, Any]:
        if not spec.payload_field:
            return {}
        payload = row.get(spec.payload_field)
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _extract_raw_score(*, hit: dict[str, Any]) -> float | None:
        for key in ("distance", "score"):
            value = hit.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    def _build_fetch_output_fields(self, *, spec: CollectionSpec) -> list[str]:
        fields = [
            spec.id_field,
            spec.text_field,
            spec.vector_field,
            *scalar_field_names(spec=spec),
        ]
        if spec.payload_field:
            fields.append(spec.payload_field)
        return fields

    def _build_search_output_fields(self, *, spec: CollectionSpec, request: SearchRequest) -> list[str]:
        fields = [
            spec.text_field,
            *scalar_field_names(spec=spec),
        ]
        if spec.payload_field and request.include_payload:
            fields.append(spec.payload_field)
        for field in request.output_fields:
            if field not in fields and field != spec.vector_field:
                fields.append(field)
        return fields

    def _build_filter_expression(
        self,
        *,
        spec: CollectionSpec,
        ids: Sequence[str] | None,
        filters: Sequence[FilterCondition] | None,
    ) -> str:
        expressions: list[str] = []
        if ids:
            expressions.append(
                self._build_in_expression(
                    field=spec.id_field,
                    values=list(ids),
                )
            )
        for condition in filters or []:
            expressions.append(self._translate_filter_condition(condition=condition))
        return " and ".join(f"({expr})" for expr in expressions if expr)

    def _translate_filter_condition(self, *, condition: FilterCondition) -> str:
        if condition.op == FilterOperator.IN:
            if not isinstance(condition.value, list):
                raise UnsupportedFilterError("IN 过滤器的 value 必须为 list")
            return self._build_in_expression(
                field=condition.field,
                values=condition.value,
            )

        if isinstance(condition.value, list):
            raise UnsupportedFilterError(f"{condition.op.value} 过滤器的 value 不能为 list")

        operator_map = {
            FilterOperator.EQ: "==",
            FilterOperator.NE: "!=",
            FilterOperator.LT: "<",
            FilterOperator.LTE: "<=",
            FilterOperator.GT: ">",
            FilterOperator.GTE: ">=",
        }
        operator = operator_map[condition.op]
        return f"{condition.field} {operator} {self._format_scalar(condition.value)}"

    def _build_in_expression(self, *, field: str, values: Sequence[Any]) -> str:
        if not values:
            raise UnsupportedFilterError("IN 过滤器不能为空")
        formatted_values = ", ".join(self._format_scalar(value) for value in values)
        return f"{field} in [{formatted_values}]"

    def _map_data_type(self, data_type: ScalarDataType) -> DataType:
        mapping = {
            ScalarDataType.INT64: DataType.INT64,
            ScalarDataType.FLOAT: DataType.FLOAT,
            ScalarDataType.BOOL: DataType.BOOL,
            ScalarDataType.STRING: DataType.VARCHAR,
            ScalarDataType.JSON: DataType.JSON,
        }
        return mapping[data_type]

    def _map_metric_type(self, metric_type: MetricType) -> str:
        mapping = {
            MetricType.COSINE: "COSINE",
            MetricType.IP: "IP",
            MetricType.L2: "L2",
        }
        return mapping[metric_type]

    def _format_scalar(self, value: Any) -> str:
        if isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace("'", "\\'")
            return f"'{escaped}'"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        raise UnsupportedFilterError(f"不支持的过滤值类型: {type(value)!r}")

    def _normalize_score(
        self,
        *,
        metric_type: MetricType,
        raw_score: float | None,
    ) -> float | None:
        if raw_score is None:
            return None
        if metric_type == MetricType.L2:
            return 1.0 / (1.0 + max(raw_score, 0.0))
        return raw_score


MILVUS_HOST = "localhost"
MILVUS_PORT = 19530


def create_milvus_backend(
    *,
    uri: str = f"http://{MILVUS_HOST}:{MILVUS_PORT}",
    token: str | None = None,
    db_name: str | None = None,
    timeout: float | None = None,
) -> VectorBackend:
    return MilvusBackend(
        uri=uri,
        token=token,
        db_name=db_name,
        timeout=timeout,
    )
