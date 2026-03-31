from __future__ import annotations

import contextlib

from pymilvus import MilvusClient, connections

from .backend import MilvusBackend
from .types import FullTextSearchSpec, MILVUS_HOST, MILVUS_PORT, MilvusCollectionSpec


def connect_milvus(
    *,
    uri: str | None = None,
    token: str | None = None,
    db_name: str | None = None,
    timeout: float | None = None,
) -> bool:
    backend = create_milvus_backend(
        uri=uri,
        token=token,
        db_name=db_name,
        timeout=timeout,
    )

    try:
        backend.client.get_server_version()
        return True
    except Exception:
        backend.close()
        return False


def disconnect_milvus(
    *,
    uri: str | None = None,
    token: str | None = None,
    db_name: str | None = None,
    timeout: float | None = None,
) -> None:
    backend = create_milvus_backend(
        uri=uri,
        token=token,
        db_name=db_name,
        timeout=timeout,
    )
    backend.shutdown()

    with contextlib.suppress(Exception):
        if connections.has_connection("default"):
            connections.disconnect("default")


def create_milvus_backend(
    *,
    uri: str | None = None,
    token: str | None = None,
    db_name: str | None = None,
    timeout: float | None = None,
) -> MilvusBackend:
    resolved_uri = uri if uri is not None else f"http://{MILVUS_HOST}:{MILVUS_PORT}"
    return MilvusBackend(
        uri=resolved_uri,
        token=token,
        db_name=db_name,
        timeout=timeout,
    )


__all__ = [
    "FullTextSearchSpec",
    "MilvusBackend",
    "MilvusCollectionSpec",
    "MilvusClient",
    "connect_milvus",
    "connections",
    "create_milvus_backend",
    "disconnect_milvus",
]
