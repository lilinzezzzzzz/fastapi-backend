from pkg.vectors.repositories.base import BaseVectorRepository

__all__ = ["BaseVectorRepository"]

try:
    from pkg.vectors.repositories.chunks import (
        ChunkVectorDocument,
        ChunkVectorRepository,
        new_chunk_repository,
    )
except ModuleNotFoundError:
    pass
else:
    __all__.extend(
        [
            "ChunkVectorDocument",
            "ChunkVectorRepository",
            "new_chunk_repository",
        ]
    )

try:
    from pkg.vectors.repositories.qa_pairs import (
        QaPairVectorDocument,
        QaPairVectorRepository,
        new_qa_pair_repository,
    )
except ModuleNotFoundError:
    pass
else:
    __all__.extend(
        [
            "QaPairVectorDocument",
            "QaPairVectorRepository",
            "new_qa_pair_repository",
        ]
    )
