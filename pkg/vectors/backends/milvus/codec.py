from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pkg.vectors.backends.base import CollectionSpec, MetricType, scalar_field_names
from pkg.vectors.contracts import (
    FilterCondition,
    FilterOperator,
    SearchHit,
    SearchRequest,
    VectorRecord,
)
from pkg.vectors.errors import UnsupportedFilterError


def record_to_row(*, spec: CollectionSpec, record: VectorRecord) -> dict[str, Any]:
    row: dict[str, Any] = {
        spec.id_field: record.id,
        spec.text_field: record.text,
        spec.vector_field: record.embedding,
    }
    if spec.payload_field:
        row[spec.payload_field] = record.payload
    row.update(record.metadata)
    return row


def row_to_record(*, spec: CollectionSpec, row: dict[str, Any]) -> VectorRecord:
    metadata = {
        field.name: row[field.name]
        for field in spec.scalar_fields
        if field.name in row
    }
    payload = {}
    if spec.payload_field:
        payload_value = row.get(spec.payload_field)
        if isinstance(payload_value, dict):
            payload = payload_value

    embedding = row.get(spec.vector_field)
    return VectorRecord(
        id=coerce_id_value(row.get(spec.id_field)),
        text=str(row.get(spec.text_field, "")),
        embedding=embedding if isinstance(embedding, list) else None,
        metadata=metadata,
        payload=payload,
    )


def hit_to_search_hit(*, spec: CollectionSpec, hit: dict[str, Any]) -> SearchHit:
    row = extract_entity_row(spec=spec, hit=hit)
    raw_score = extract_raw_score(hit=hit)
    return SearchHit(
        id=coerce_id_value(hit.get("id", row.get(spec.id_field))),
        text=row.get(spec.text_field),
        metadata={
            field.name: row[field.name]
            for field in spec.scalar_fields
            if field.name in row
        },
        payload=extract_payload(spec=spec, row=row),
        relevance_score=normalize_score(
            metric_type=spec.metric_type,
            raw_score=raw_score,
        ),
        raw_score=raw_score,
    )


def extract_entity_row(*, spec: CollectionSpec, hit: dict[str, Any]) -> dict[str, Any]:
    entity = hit.get("entity")
    if isinstance(entity, dict):
        return dict(entity)

    row = {
        key: value
        for key, value in hit.items()
        if key not in {"id", "distance", "score", "entity"}
    }
    if spec.id_field not in row and "id" in hit:
        row[spec.id_field] = hit["id"]
    return row


def extract_payload(*, spec: CollectionSpec, row: dict[str, Any]) -> dict[str, Any]:
    if not spec.payload_field:
        return {}
    payload = row.get(spec.payload_field)
    return payload if isinstance(payload, dict) else {}


def extract_raw_score(*, hit: dict[str, Any]) -> float | None:
    for key in ("distance", "score"):
        value = hit.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def build_fetch_output_fields(*, spec: CollectionSpec) -> list[str]:
    fields = [
        spec.id_field,
        spec.text_field,
        spec.vector_field,
        *scalar_field_names(spec=spec),
    ]
    if spec.payload_field:
        fields.append(spec.payload_field)
    return fields


def build_search_output_fields(
    *,
    spec: CollectionSpec,
    request: SearchRequest,
) -> list[str]:
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


def build_filter_expression(
    *,
    spec: CollectionSpec,
    ids: Sequence[int] | None,
    filters: Sequence[FilterCondition] | None,
) -> str:
    expressions: list[str] = []
    if ids:
        expressions.append(
            build_in_expression(
                field=spec.id_field,
                values=list(ids),
            )
        )
    for condition in filters or []:
        expressions.append(translate_filter_condition(condition=condition))
    return " and ".join(f"({expr})" for expr in expressions if expr)


def translate_filter_condition(*, condition: FilterCondition) -> str:
    if condition.op == FilterOperator.IN:
        if not isinstance(condition.value, list):
            raise UnsupportedFilterError("IN 过滤器的 value 必须为 list")
        return build_in_expression(
            field=condition.field,
            values=condition.value,
        )

    if isinstance(condition.value, list):
        raise UnsupportedFilterError(
            f"{condition.op.value} 过滤器的 value 不能为 list"
        )

    operator_map = {
        FilterOperator.EQ: "==",
        FilterOperator.NE: "!=",
        FilterOperator.LT: "<",
        FilterOperator.LTE: "<=",
        FilterOperator.GT: ">",
        FilterOperator.GTE: ">=",
    }
    operator = operator_map[condition.op]
    return f"{condition.field} {operator} {format_scalar(condition.value)}"


def build_in_expression(*, field: str, values: Sequence[Any]) -> str:
    if not values:
        raise UnsupportedFilterError("IN 过滤器不能为空")
    formatted_values = ", ".join(format_scalar(value) for value in values)
    return f"{field} in [{formatted_values}]"


def format_scalar(value: Any) -> str:
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    raise UnsupportedFilterError(f"不支持的过滤值类型: {type(value)!r}")


def coerce_id_value(value: Any) -> int:
    if isinstance(value, bool):
        raise UnsupportedFilterError("不支持将 bool 作为主键值")
    return int(value)


def normalize_score(
    *,
    metric_type: MetricType,
    raw_score: float | None,
) -> float | None:
    if raw_score is None:
        return None
    if metric_type == MetricType.L2:
        return 1.0 / (1.0 + max(raw_score, 0.0))
    return raw_score
