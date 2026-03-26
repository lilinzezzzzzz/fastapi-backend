from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from pkg.vectors.backends.base import CollectionSpec, EmptyIndexParams, IndexConfig, IndexParams


class MilvusDenseIndexType(StrEnum):
    AUTOINDEX = "AUTOINDEX"
    FLAT = "FLAT"
    HNSW = "HNSW"
    IVF_FLAT = "IVF_FLAT"
    IVF_SQ8 = "IVF_SQ8"
    IVF_PQ = "IVF_PQ"
    DISKANN = "DISKANN"


class MilvusSparseIndexType(StrEnum):
    SPARSE_INVERTED_INDEX = "SPARSE_INVERTED_INDEX"


class MilvusConsistencyLevel(StrEnum):
    STRONG = "Strong"
    SESSION = "Session"
    BOUNDED = "Bounded"
    EVENTUALLY = "Eventually"
    CUSTOMIZED = "Customized"


class MilvusHnswIndexParams(IndexParams):
    M: int | None = Field(default=None, gt=0)
    efConstruction: int | None = Field(default=None, gt=0)


class MilvusIvfIndexParams(IndexParams):
    nlist: int | None = Field(default=None, gt=0)


class MilvusIvfPqIndexParams(MilvusIvfIndexParams):
    m: int | None = Field(default=None, gt=0)
    nbits: int | None = Field(default=None, gt=0)


class MilvusSparseInvertedIndexParams(IndexParams):
    drop_ratio_build: float | None = Field(default=None, ge=0.0, le=1.0)


class MilvusAutoIndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[MilvusDenseIndexType.AUTOINDEX] = MilvusDenseIndexType.AUTOINDEX
    params: EmptyIndexParams = Field(default_factory=EmptyIndexParams)


class MilvusFlatIndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[MilvusDenseIndexType.FLAT] = MilvusDenseIndexType.FLAT
    params: EmptyIndexParams = Field(default_factory=EmptyIndexParams)


class MilvusHnswIndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[MilvusDenseIndexType.HNSW] = MilvusDenseIndexType.HNSW
    params: MilvusHnswIndexParams = Field(default_factory=MilvusHnswIndexParams)


class MilvusIvfFlatIndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[MilvusDenseIndexType.IVF_FLAT] = MilvusDenseIndexType.IVF_FLAT
    params: MilvusIvfIndexParams = Field(default_factory=MilvusIvfIndexParams)


class MilvusIvfSq8IndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[MilvusDenseIndexType.IVF_SQ8] = MilvusDenseIndexType.IVF_SQ8
    params: MilvusIvfIndexParams = Field(default_factory=MilvusIvfIndexParams)


class MilvusIvfPqIndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[MilvusDenseIndexType.IVF_PQ] = MilvusDenseIndexType.IVF_PQ
    params: MilvusIvfPqIndexParams = Field(default_factory=MilvusIvfPqIndexParams)


class MilvusDiskAnnIndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[MilvusDenseIndexType.DISKANN] = MilvusDenseIndexType.DISKANN
    params: EmptyIndexParams = Field(default_factory=EmptyIndexParams)


type MilvusIndexConfig = Annotated[
    MilvusAutoIndexConfig
    | MilvusFlatIndexConfig
    | MilvusHnswIndexConfig
    | MilvusIvfFlatIndexConfig
    | MilvusIvfSq8IndexConfig
    | MilvusIvfPqIndexConfig
    | MilvusDiskAnnIndexConfig,
    Field(discriminator="index_type"),
]


class MilvusSparseInvertedIndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[MilvusSparseIndexType.SPARSE_INVERTED_INDEX] = MilvusSparseIndexType.SPARSE_INVERTED_INDEX
    params: MilvusSparseInvertedIndexParams = Field(default_factory=MilvusSparseInvertedIndexParams)


type MilvusSparseIndexConfig = Annotated[
    MilvusSparseInvertedIndexConfig,
    Field(discriminator="index_type"),
]


class FullTextSearchSpec(BaseModel, extra="forbid"):
    """Milvus BM25 / full-text search 配置。"""

    enabled: bool = False
    sparse_vector_field: str = Field(default="text_sparse", min_length=1)
    function_name: str = Field(default="text_bm25_emb", min_length=1)
    analyzer_params: dict[str, object] = Field(default_factory=dict)
    function_params: dict[str, object] = Field(default_factory=dict)
    index_config: MilvusSparseIndexConfig = Field(default_factory=MilvusSparseInvertedIndexConfig)
    description: str = ""


class MilvusCollectionSpec(CollectionSpec, extra="forbid"):
    """Milvus collection 规格定义。"""

    index_config: MilvusIndexConfig = Field(default_factory=MilvusAutoIndexConfig)
    full_text_search: FullTextSearchSpec = Field(default_factory=FullTextSearchSpec)
    consistency_level: MilvusConsistencyLevel = MilvusConsistencyLevel.SESSION
    enable_dynamic_field: bool = False
