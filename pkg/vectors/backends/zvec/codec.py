from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from zvec import Doc

from pkg.vectors.backends.base import CollectionSpec, MetricType
from pkg.vectors.contracts import (
    FilterCondition,
    FilterOperator,
    SearchHit,
    VectorRecord,
)
from pkg.vectors.errors import UnsupportedFilterError


def record_to_doc(*, spec: CollectionSpec, record: VectorRecord) -> Doc:
    fields: dict[str, Any] = {
        spec.text_field: record.text,
        **record.metadata,
    }
    if spec.payload_field:
        fields[spec.payload_field] = json.dumps(record.payload, ensure_ascii=False)
    return Doc(
        id=str(record.id),
        fields=fields,
        vectors={spec.vector_field: record.embedding},
    )


def doc_to_record(*, spec: CollectionSpec, doc: Doc) -> VectorRecord:
    fields = doc.fields or {}
    payload: dict[str, Any] = {}
    if spec.payload_field:
        payload = decode_payload(raw=fields.get(spec.payload_field))

    return VectorRecord(
        id=coerce_doc_id(value=doc.id),
        text=str(fields.get(spec.text_field, "")),
        embedding=extract_vector(doc=doc, field_name=spec.vector_field),
        metadata={
            field.name: fields[field.name]
            for field in spec.scalar_fields
            if field.name in fields
        },
        payload=payload,
    )


def doc_to_search_hit(
    *,
    spec: CollectionSpec,
    doc: Doc,
    include_payload: bool,
) -> SearchHit:
    fields = doc.fields or {}
    raw_score = float(doc.score) if doc.score is not None else None
    payload = decode_payload(raw=fields.get(spec.payload_field)) if spec.payload_field else {}
    return SearchHit(
        id=coerce_doc_id(value=doc.id),
        text=str(fields.get(spec.text_field, "")),
        metadata={
            field.name: fields[field.name]
            for field in spec.scalar_fields
            if field.name in fields
        },
        payload=payload if include_payload else {},
        relevance_score=normalize_score(metric_type=spec.metric_type, raw_score=raw_score),
        raw_score=raw_score,
    )


def decode_payload(*, raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def extract_vector(*, doc: Doc, field_name: str) -> list[float] | None:
    if not doc.vectors:
        return None
    value = doc.vector(field_name)
    return value if isinstance(value, list) else None


def coerce_doc_id(*, value: Any) -> int:
    if isinstance(value, bool):
        raise UnsupportedFilterError("不支持将 bool 作为主键值")
    return int(value)


def build_filter_expression(
    *,
    spec: CollectionSpec,
    ids: Sequence[int] | None,
    filters: Sequence[FilterCondition] | None,
) -> str:
    expressions: list[str] = []
    if ids:
        expressions.append(build_in_expression(field=spec.id_field, values=list(ids)))
    for condition in filters or []:
        expressions.append(translate_filter_condition(condition=condition))
    return " AND ".join(f"({expr})" for expr in expressions if expr)


def translate_filter_condition(*, condition: FilterCondition) -> str:
    if condition.op == FilterOperator.IN:
        if not isinstance(condition.value, list):
            raise UnsupportedFilterError("IN 过滤器的 value 必须为 list")
        return build_in_expression(
            field=condition.field,
            values=condition.value,
        )

    if isinstance(condition.value, list):
        raise UnsupportedFilterError(f"{condition.op.value} 过滤器的 value 不能为 list")

    operator_map = {
        FilterOperator.EQ: "=",
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
    return f"{field} IN ({formatted_values})"


def format_scalar(value: Any) -> str:
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{escaped}'"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    raise UnsupportedFilterError(f"不支持的过滤值类型: {type(value)!r}")


def extract_delete_count(*, result: Any, fallback: int) -> int:
    if isinstance(result, bool):
        return fallback if result else 0
    if isinstance(result, int):
        return result
    if isinstance(result, float):
        return int(result)
    if isinstance(result, dict):
        for key in ("delete_count", "count", "deleted"):
            value = result.get(key)
            if isinstance(value, (int, float)):
                return int(value)
    return fallback


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
