from __future__ import annotations

import contextlib
from functools import cache

from pymilvus import MilvusClient, connections

from .backend import MilvusBackend

MILVUS_HOST = "localhost"
MILVUS_PORT = 19530


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
    return _create_milvus_backend_cached(
        uri=resolved_uri,
        token=token,
        db_name=db_name,
        timeout=timeout,
    )


@cache
def _create_milvus_backend_cached(
    *,
    uri: str,
    token: str | None = None,
    db_name: str | None = None,
    timeout: float | None = None,
) -> MilvusBackend:
    return MilvusBackend(
        uri=uri,
        token=token,
        db_name=db_name,
        timeout=timeout,
    )


__all__ = [
    "MilvusBackend",
    "MilvusClient",
    "connect_milvus",
    "connections",
    "create_milvus_backend",
    "disconnect_milvus",
]
