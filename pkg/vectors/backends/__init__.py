from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pkg.vectors.backends.base import (
    BackendProvider,
    BaseVectorBackend,
    CollectionSpec,
    ConsistencyLevel,
    FullTextSearchSpec,
    MetricType,
    ScalarDataType,
    ScalarFieldSpec,
    TenantIsolationMode,
    VectorBackend,
)
from pkg.vectors.backends.milvus import MilvusBackend, create_milvus_backend

if TYPE_CHECKING:
    from pkg.vectors.backends.zvec import ZvecBackend


def create_zvec_backend(**kwargs: Any) -> VectorBackend:
    from pkg.vectors.backends.zvec import create_zvec_backend as _create_zvec_backend

    return _create_zvec_backend(**kwargs)


BACKEND_BUILDERS: dict[BackendProvider, Callable[..., VectorBackend]] = {
    BackendProvider.MILVUS: create_milvus_backend,
    BackendProvider.ZVEC: create_zvec_backend,
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
    "ConsistencyLevel",
    "FullTextSearchSpec",
    "MetricType",
    "MilvusBackend",
    "ScalarDataType",
    "ScalarFieldSpec",
    "TenantIsolationMode",
    "VectorBackend",
    "ZvecBackend",
    "create_backend",
    "create_zvec_backend",
]


def __getattr__(name: str) -> Any:
    if name == "ZvecBackend":
        from pkg.vectors.backends.zvec import ZvecBackend

        return ZvecBackend
    raise AttributeError(name)
