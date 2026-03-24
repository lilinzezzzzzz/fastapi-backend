from __future__ import annotations

from .backend import ZvecBackend


def create_zvec_backend(
    *,
    root_path: str,
    read_only: bool = False,
    enable_mmap: bool = True,
) -> ZvecBackend:
    return ZvecBackend(
        root_path=root_path,
        read_only=read_only,
        enable_mmap=enable_mmap,
    )


__all__ = [
    "ZvecBackend",
    "create_zvec_backend",
]
