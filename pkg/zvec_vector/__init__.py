"""
Zvec 向量数据库操作模块

提供向量数据库操作的基类和配置类。
参考文档: https://zvec.org/en/docs/quickstart/
"""

from pkg.zvec_vector.base import (
    BaseVectorStore,
    CollectionConfig,
    IndexType,
    ScalarFieldConfig,
    SearchParams,
    SearchResult,
    VectorDataType,
    VectorFieldConfig,
    VectorMetricType,
)

__all__ = [
    "BaseVectorStore",
    "CollectionConfig",
    "IndexType",
    "ScalarFieldConfig",
    "SearchParams",
    "SearchResult",
    "VectorDataType",
    "VectorFieldConfig",
    "VectorMetricType",
]
