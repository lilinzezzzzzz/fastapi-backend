from __future__ import annotations

import contextlib
from typing import Any

from pymilvus import DataType, Function, FunctionType, MilvusClient

from pkg.vectors.backends.base import CollectionSpec, MetricType, ScalarDataType
from pkg.vectors.errors import CollectionSchemaMismatchError


def validate_collection_description(
    *,
    description: object,
    spec: CollectionSpec,
) -> None:
    if not isinstance(description, dict):
        raise CollectionSchemaMismatchError(
            f"Milvus collection 描述格式非法: collection={spec.name}, description_type={type(description)!r}"
        )

    raw_fields: object = description.get("fields")
    if not isinstance(raw_fields, list):
        raise CollectionSchemaMismatchError(f"Milvus collection 缺少 fields 描述: collection={spec.name}")

    field_map: dict[str, dict[str, Any]] = {}
    for field in raw_fields:
        if isinstance(field, dict) and isinstance(field.get("name"), str):
            field_map[field["name"]] = field

    for required_field in [spec.id_field, spec.text_field, spec.vector_field]:
        if required_field not in field_map:
            raise CollectionSchemaMismatchError(
                f"Milvus collection 字段缺失: collection={spec.name}, field={required_field}"
            )

    id_field = field_map[spec.id_field]
    text_field = field_map[spec.text_field]
    vector_field = field_map[spec.vector_field]
    _validate_field_type(
        collection_name=spec.name,
        field_name=spec.id_field,
        field=id_field,
        expected=DataType.INT64,
        label="主键",
    )
    _validate_field_type(
        collection_name=spec.name,
        field_name=spec.text_field,
        field=text_field,
        expected=DataType.VARCHAR,
        label="文本",
    )
    _validate_field_type(
        collection_name=spec.name,
        field_name=spec.vector_field,
        field=vector_field,
        expected=DataType.FLOAT_VECTOR,
        label="向量",
    )

    if spec.payload_field and spec.payload_field not in field_map:
        raise CollectionSchemaMismatchError(
            f"Milvus collection 缺少 payload 字段: collection={spec.name}, field={spec.payload_field}"
        )

    if spec.payload_field:
        _validate_field_type(
            collection_name=spec.name,
            field_name=spec.payload_field,
            field=field_map[spec.payload_field],
            expected=DataType.JSON,
            label="payload",
        )

    for scalar_field in spec.scalar_fields:
        if scalar_field.name not in field_map:
            raise CollectionSchemaMismatchError(
                f"Milvus collection 缺少 metadata 字段: collection={spec.name}, field={scalar_field.name}"
            )
        _validate_field_type(
            collection_name=spec.name,
            field_name=scalar_field.name,
            field=field_map[scalar_field.name],
            expected=map_data_type(scalar_field.data_type),
            label="metadata",
        )

    if spec.full_text_search.enabled:
        sparse_field_name = spec.full_text_search.sparse_vector_field
        sparse_field = field_map.get(sparse_field_name)
        if sparse_field is None:
            raise CollectionSchemaMismatchError(
                f"Milvus collection 缺少 BM25 sparse 字段: collection={spec.name}, field={sparse_field_name}"
            )
        _validate_field_type(
            collection_name=spec.name,
            field_name=sparse_field_name,
            field=sparse_field,
            expected=DataType.SPARSE_FLOAT_VECTOR,
            label="BM25 sparse",
        )

        text_params = text_field.get("params")
        if not isinstance(text_params, dict) or not text_params.get("enable_analyzer", False):
            raise CollectionSchemaMismatchError(
                f"Milvus full-text 字段未启用 analyzer: collection={spec.name}, field={spec.text_field}"
            )

        raw_functions: object = description.get("functions")
        if not isinstance(raw_functions, list):
            raise CollectionSchemaMismatchError(f"Milvus collection 缺少 functions 描述: collection={spec.name}")
        function_exists = any(
            isinstance(function, dict)
            and _matches_data_type(function.get("type"), FunctionType.BM25)
            and function.get("name") == spec.full_text_search.function_name
            and function.get("input_field_names") == [spec.text_field]
            and function.get("output_field_names") == [sparse_field_name]
            for function in raw_functions
        )
        if not function_exists:
            raise CollectionSchemaMismatchError(
                f"Milvus collection 缺少 BM25 function: collection={spec.name}, function={spec.full_text_search.function_name}"
            )

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
        enable_analyzer=spec.full_text_search.enabled,
        **spec.full_text_search.analyzer_params,
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

    if spec.full_text_search.enabled:
        schema.add_field(
            field_name=spec.full_text_search.sparse_vector_field,
            datatype=DataType.SPARSE_FLOAT_VECTOR,
        )
        schema.add_function(
            Function(
                name=spec.full_text_search.function_name,
                function_type=FunctionType.BM25,
                input_field_names=[spec.text_field],
                output_field_names=[spec.full_text_search.sparse_vector_field],
                description=spec.full_text_search.description,
                params=spec.full_text_search.function_params or None,
            )
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

    if spec.full_text_search.enabled:
        sparse_index_config = dict(spec.full_text_search.index_config)
        sparse_index_params = dict(sparse_index_config.pop("params", {}))
        index_params.add_index(
            field_name=spec.full_text_search.sparse_vector_field,
            index_name=sparse_index_config.pop(
                "index_name",
                f"idx_{spec.full_text_search.sparse_vector_field}",
            ),
            index_type=sparse_index_config.pop(
                "index_type",
                "SPARSE_INVERTED_INDEX",
            ),
            metric_type=sparse_index_config.pop("metric_type", "BM25"),
            params=sparse_index_params,
            **sparse_index_config,
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


def _validate_field_type(
    *,
    collection_name: str,
    field_name: str,
    field: dict[str, Any],
    expected: DataType,
    label: str,
) -> None:
    actual = field.get("type")
    if _matches_data_type(actual, expected):
        return
    raise CollectionSchemaMismatchError(
        f"{label}字段类型不匹配: collection={collection_name}, field={field_name}, got={actual}, expected={expected.name}"
    )


def _matches_data_type(actual: object, expected: object) -> bool:
    expected_normalized = _normalize_type_name(expected)
    if expected_normalized is None:
        return False
    actual_normalized = _normalize_type_name(actual)
    return actual_normalized == expected_normalized


def _normalize_type_name(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (DataType, FunctionType)):
        return _normalize_type_name(value.name)
    if isinstance(value, int):
        for enum_type in (DataType, FunctionType):
            with contextlib.suppress(ValueError):
                return _normalize_type_name(enum_type(value).name)
        return str(value)
    if isinstance(value, str):
        return "".join(char for char in value.upper() if char.isalnum())
    return None
