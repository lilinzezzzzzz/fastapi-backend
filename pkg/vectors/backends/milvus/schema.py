from __future__ import annotations

from typing import Any

from pymilvus import DataType, MilvusClient

from pkg.vectors.backends.base import CollectionSpec, MetricType, ScalarDataType
from pkg.vectors.errors import CollectionSchemaMismatchError


def validate_collection_description(
    *,
    description: object,
    spec: CollectionSpec,
) -> None:
    if not isinstance(description, dict):
        return

    raw_fields: object = description.get("fields")
    if not isinstance(raw_fields, list):
        return

    field_map: dict[str, dict[str, Any]] = {}
    for field in raw_fields:
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


def build_schema(*, spec: CollectionSpec):
    schema = MilvusClient.create_schema(
        auto_id=False,
        enable_dynamic_field=spec.enable_dynamic_field,
    )
    schema.add_field(
        field_name=spec.id_field,
        datatype=DataType.INT64,
        is_primary=True,
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
            datatype=map_data_type(field.data_type),
            **kwargs,
        )

    return schema


def build_index_params(*, client: MilvusClient, spec: CollectionSpec):
    index_params = client.prepare_index_params()
    index_config = dict(spec.index_config)
    vector_index_params = dict(index_config.pop("params", {}))
    index_params.add_index(
        field_name=spec.vector_field,
        index_name=index_config.pop("index_name", f"idx_{spec.vector_field}"),
        index_type=index_config.pop("index_type", "AUTOINDEX"),
        metric_type=index_config.pop(
            "metric_type",
            map_metric_type(spec.metric_type),
        ),
        params=vector_index_params,
        **index_config,
    )
    return index_params


def map_data_type(data_type: ScalarDataType) -> DataType:
    mapping = {
        ScalarDataType.INT64: DataType.INT64,
        ScalarDataType.FLOAT: DataType.FLOAT,
        ScalarDataType.BOOL: DataType.BOOL,
        ScalarDataType.STRING: DataType.VARCHAR,
        ScalarDataType.JSON: DataType.JSON,
    }
    return mapping[data_type]


def map_metric_type(metric_type: MetricType) -> str:
    mapping = {
        MetricType.COSINE: "COSINE",
        MetricType.IP: "IP",
        MetricType.L2: "L2",
    }
    return mapping[metric_type]
