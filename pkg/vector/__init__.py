from pkg.vector.backends import (
    BACKEND_BUILDERS,
    BackendProvider,
    BaseVectorBackend,
    CollectionSpec,
    ConsistencyLevel,
    MetricType,
    MilvusBackend,
    ScalarDataType,
    ScalarFieldSpec,
    TenantIsolationMode,
    VectorBackend,
    create_backend,
)
from pkg.vector.capabilities import (
    SupportsBulkImport,
    SupportsHybridSearch,
    SupportsLoadControl,
    SupportsNamespaceIsolation,
)
from pkg.vector.contracts import (
    FilterCondition,
    FilterOperator,
    SearchHit,
    SearchRequest,
    VectorRecord,
)
from pkg.vector.embedders import (
    EMBEDDER_BUILDERS,
    EmbedderProvider,
    LLMEmbedder,
    create_embedder,
)
from pkg.vector.errors import (
    CapabilityNotSupportedError,
    CollectionSchemaMismatchError,
    InvalidEmbeddingDimensionError,
    RecordValidationError,
    UnsupportedFilterError,
    VectorCoreError,
)
from pkg.vector.repositories import BaseVectorRepository

__all__ = [
    "BACKEND_BUILDERS",
    "BackendProvider",
    "BaseVectorBackend",
    "BaseVectorRepository",
    "CapabilityNotSupportedError",
    "CollectionSchemaMismatchError",
    "CollectionSpec",
    "ConsistencyLevel",
    "EMBEDDER_BUILDERS",
    "EmbedderProvider",
    "FilterCondition",
    "FilterOperator",
    "InvalidEmbeddingDimensionError",
    "LLMEmbedder",
    "MetricType",
    "MilvusBackend",
    "RecordValidationError",
    "ScalarDataType",
    "ScalarFieldSpec",
    "SearchHit",
    "SearchRequest",
    "SupportsBulkImport",
    "SupportsHybridSearch",
    "SupportsLoadControl",
    "SupportsNamespaceIsolation",
    "TenantIsolationMode",
    "UnsupportedFilterError",
    "VectorBackend",
    "VectorCoreError",
    "VectorRecord",
    "create_backend",
    "create_embedder",
]

try:
    from pkg.vector.repositories import (
        ChunkVectorDocument,
        ChunkVectorRepository,
        QaPairVectorDocument,
        QaPairVectorRepository,
    )
except ImportError:
    pass
else:
    __all__.extend(
        [
            "ChunkVectorDocument",
            "ChunkVectorRepository",
            "QaPairVectorDocument",
            "QaPairVectorRepository",
        ]
    )
