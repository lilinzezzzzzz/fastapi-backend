from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pkg.vectors.backends.base import (
    BackendProvider,
    BaseVectorBackend,
    CollectionSpec,
    ScalarDataType,
    ScalarFieldSpec,
    TenantIsolationMode,
    VectorBackend,
)
from pkg.vectors.backends.milvus import MetricType, MilvusBackend, create_milvus_backend

BACKEND_BUILDERS: dict[BackendProvider, Callable[..., VectorBackend]] = {
    BackendProvider.MILVUS: create_milvus_backend,
}


def create_backend(*, provider: BackendProvider, **kwargs: Any) -> VectorBackend:
    provider_enum = BackendProvider.is_valid(provider)
    try:
        builder = BACKEND_BUILDERS[provider_enum]
    except KeyError as exc:
        raise ValueError(f"unsupported backend provider: {provider_enum}") from exc
    return builder(**kwargs)


__all__ = [
    "BACKEND_BUILDERS",
    "BaseVectorBackend",
    "BackendProvider",
    "CollectionSpec",
    "MetricType",
    "MilvusBackend",
    "ScalarDataType",
    "ScalarFieldSpec",
    "TenantIsolationMode",
    "VectorBackend",
    "create_backend",
]
