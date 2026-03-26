from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from pkg.vectors.backends.base import CollectionSpec, EmptyIndexParams, IndexConfig


class ZvecIndexType(StrEnum):
    FLAT = "FLAT"
    HNSW = "HNSW"
    IVF = "IVF"


class ZvecFlatIndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[ZvecIndexType.FLAT] = ZvecIndexType.FLAT
    params: EmptyIndexParams = Field(default_factory=EmptyIndexParams)


class ZvecHnswIndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[ZvecIndexType.HNSW] = ZvecIndexType.HNSW
    params: EmptyIndexParams = Field(default_factory=EmptyIndexParams)


class ZvecIvfIndexConfig(IndexConfig, extra="forbid"):
    index_type: Literal[ZvecIndexType.IVF] = ZvecIndexType.IVF
    params: EmptyIndexParams = Field(default_factory=EmptyIndexParams)


type ZvecIndexConfig = Annotated[
    ZvecFlatIndexConfig | ZvecHnswIndexConfig | ZvecIvfIndexConfig,
    Field(discriminator="index_type"),
]


class ZvecCollectionSpec(CollectionSpec, extra="forbid"):
    """zvec collection 规格定义。"""

    index_config: ZvecIndexConfig = Field(default_factory=ZvecFlatIndexConfig)
