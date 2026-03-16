from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Any

from pkg.vector.embedders.base import BaseEmbedder, Embedder, EmbedderProvider
from pkg.vector.embedders.llm import LLMEmbedder, create_llm_embedder

_NO_AUTH_API_KEY = "not-required"

EMBEDDER_BUILDERS: dict[EmbedderProvider, Callable[..., Embedder]] = {
    EmbedderProvider.LLM: create_llm_embedder,
}


def create_embedder(*, provider: EmbedderProvider, **kwargs: Any) -> Embedder:
    if not isinstance(provider, EmbedderProvider):
        raise TypeError(f"非法 embedder provider: {provider}")
    try:
        builder = EMBEDDER_BUILDERS[provider]
    except KeyError as exc:
        raise ValueError(f"unsupported embedder provider: {provider}") from exc
    return builder(**kwargs)


@lru_cache(maxsize=32)
def _build_cached_embedder(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
) -> Embedder:
    """以实际配置参数为 key 缓存 Embedder 实例。

    使用配置参数（而非 organization_id）作为 cache key，
    配置变更后自动产生新 key，创建新实例；旧实例由 LRU 自然淘汰。
    """
    return create_embedder(
        provider=EmbedderProvider.LLM,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def build_embedder(
    *,
    api_key: str,
    base_url: str | None,
    model: str,
) -> Embedder:
    if not api_key and base_url:
        api_key = _NO_AUTH_API_KEY
    return _build_cached_embedder(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


__all__ = [
    "BaseEmbedder",
    "EMBEDDER_BUILDERS",
    "Embedder",
    "EmbedderProvider",
    "LLMEmbedder",
    "build_embedder",
    "create_embedder",
]
