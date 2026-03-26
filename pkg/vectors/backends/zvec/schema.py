from __future__ import annotations

from typing import Any

import zvec
from zvec import CollectionSchema

from pkg.vectors.backends.base import CollectionSpec, MetricType, ScalarDataType
from pkg.vectors.backends.zvec.specs import ZvecCollectionSpec, ZvecIndexType


def require_zvec_spec(*, spec: CollectionSpec) -> ZvecCollectionSpec:
    if not isinstance(spec, ZvecCollectionSpec):
        raise TypeError(f"zvec backend 需要 ZvecCollectionSpec，实际收到: {type(spec).__name__}")
    return spec


def build_schema(*, spec: CollectionSpec) -> CollectionSchema:
    spec = require_zvec_spec(spec=spec)
    fields = [
        zvec.FieldSchema(
            name=spec.text_field,
            data_type=zvec.DataType.STRING,
        )
    ]
    if spec.payload_field:
        fields.append(
            zvec.FieldSchema(
                name=spec.payload_field,
                data_type=zvec.DataType.STRING,
                nullable=True,
            )
        )
    fields.extend(build_scalar_fields(spec=spec))

    metric_type = map_metric_type(metric_type=spec.metric_type)
    index_type = str(spec.index_config.index_type or ZvecIndexType.FLAT).upper()
    if index_type not in {index.value for index in ZvecIndexType}:
        raise ValueError(f"zvec backend 不支持的 index_type: {index_type}")
    if index_type == "HNSW":
        index_param = zvec.HnswIndexParam(metric_type=metric_type)
    elif index_type == "IVF":
        index_param = zvec.IVFIndexParam(metric_type=metric_type)
    else:
        index_param = zvec.FlatIndexParam(metric_type=metric_type)

    vectors = [
        zvec.VectorSchema(
            name=spec.vector_field,
            data_type=zvec.DataType.VECTOR_FP32,
            dimension=spec.dimension,
            index_param=index_param,
        )
    ]
    return CollectionSchema(name=spec.name, fields=fields, vectors=vectors)


def build_scalar_fields(*, spec: CollectionSpec) -> list[Any]:
    schemas: list[Any] = []
    reserved_fields = {spec.text_field, spec.vector_field, spec.id_field}
    if spec.payload_field:
        reserved_fields.add(spec.payload_field)

    for field in spec.scalar_fields:
        if field.name in reserved_fields:
            continue
        schema_kwargs: dict[str, Any] = {
            "name": field.name,
            "data_type": map_scalar_data_type(data_type=field.data_type),
            "nullable": field.nullable,
        }
        if field.filterable:
            schema_kwargs["index_param"] = zvec.InvertIndexParam()
        schemas.append(zvec.FieldSchema(**schema_kwargs))
    return schemas


def map_metric_type(*, metric_type: MetricType) -> Any:
    mapping = {
        MetricType.COSINE: zvec.MetricType.COSINE,
        MetricType.IP: zvec.MetricType.IP,
        MetricType.L2: zvec.MetricType.L2,
    }
    return mapping[metric_type]


def map_scalar_data_type(*, data_type: ScalarDataType) -> Any:
    mapping = {
        ScalarDataType.INT64: zvec.DataType.INT64,
        ScalarDataType.FLOAT: zvec.DataType.DOUBLE,
        ScalarDataType.BOOL: zvec.DataType.BOOL,
        ScalarDataType.STRING: zvec.DataType.STRING,
        ScalarDataType.JSON: zvec.DataType.STRING,
    }
    return mapping[data_type]
