"""chars matcher 内部共享类型。"""

from __future__ import annotations

from typing import Literal, TypedDict

type PinyinCharMapping = dict[str, list[str]]


class CharShapeFeature(TypedDict, total=False):
    component_tokens: list[str]
    shape_neighbors: list[str]


type ShapeFeatureMapping = dict[str, CharShapeFeature]
type CharMatchType = Literal["char", "surname"]
type MatchType = Literal["exact", "fuzzy_exact", "prefix"]


__all__ = [
    "CharMatchType",
    "CharShapeFeature",
    "MatchType",
    "PinyinCharMapping",
    "ShapeFeatureMapping",
]
