"""根据拼音查找中文候选字。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Literal

from wordfreq import zipf_frequency

type PinyinCharMapping = dict[str, list[str]]
type CharMatchType = Literal["char", "surname"]
type MatchType = Literal["exact", "fuzzy_exact", "prefix"]


@dataclass(frozen=True)
class _FuzzyVariant:
    token: str
    fuzzy_edits: int


@dataclass(frozen=True)
class _MatchedPinyinKey:
    key: str
    match_type: MatchType
    fuzzy_edits: int
    prefix_extra_chars: int = 0


@dataclass(frozen=True)
class _RankedCandidate:
    char: str
    score: float
    first_seen: int


class CharsMatcher:
    """按拼音匹配普通汉字或姓氏候选字，并对候选结果进行全局排序。"""

    _PINYIN_SPLIT_PATTERN = re.compile(r"[\s,，;；/|]+")
    _NON_ALPHA_PATTERN = re.compile(r"[^a-z]")
    _DEFAULT_CHARS_DIR = Path(__file__).resolve().parent / "chars"

    # 输入法风格的模糊音映射表
    # 声母模糊：z/zh, c/ch, s/sh, l/n, f/h, r/l
    # 韵母模糊：an/ang, en/eng, in/ing, ian/iang, uan/uang
    _FUZZY_INITIALS: dict[str, list[str]] = {
        "z": ["zh"],
        "zh": ["z"],
        "c": ["ch"],
        "ch": ["c"],
        "s": ["sh"],
        "sh": ["s"],
        "l": ["n", "r"],
        "n": ["l"],
        "r": ["l"],
        "f": ["h"],
        "h": ["f"],
    }
    _FUZZY_FINALS: dict[str, list[str]] = {
        "an": ["ang"],
        "ang": ["an"],
        "en": ["eng"],
        "eng": ["en"],
        "in": ["ing"],
        "ing": ["in"],
        "ian": ["iang"],
        "iang": ["ian"],
        "uan": ["uang"],
        "uang": ["uan"],
    }

    _MATCH_TYPE_SCORES: dict[MatchType, float] = {
        "exact": 24.0,
        "fuzzy_exact": 12.0,
        "prefix": 0.0,
    }
    _CHAR_FREQUENCY_WEIGHT = 12.0
    _FUZZY_EDIT_PENALTY = 4.0
    _PREFIX_EXTRA_CHAR_PENALTY = 2.0

    def __init__(self, *, chars_dir: Path | None = None) -> None:
        self._chars_dir = chars_dir or self._DEFAULT_CHARS_DIR
        self._char_frequency_cache: dict[str, float] = {}

    @cached_property
    def _char_mapping(self) -> PinyinCharMapping:
        return self._load_char_mapping("chars.json")

    @cached_property
    def _surname_mapping(self) -> PinyinCharMapping:
        return self._load_char_mapping("surname_chars.json")

    def _load_char_mapping(self, file_name: str) -> PinyinCharMapping:
        data = json.loads((self._chars_dir / file_name).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{file_name} 内容格式无效，期望 dict[str, list[str]]")

        normalized: PinyinCharMapping = {}
        for key, value in data.items():
            if not isinstance(key, str) or not isinstance(value, list):
                raise ValueError(f"{file_name} 内容格式无效，期望 dict[str, list[str]]")
            normalized[key] = [item for item in value if isinstance(item, str)]
        return normalized

    @classmethod
    def _normalize_pinyin_token(cls, token: str) -> str:
        """规范化单个拼音片段，生成后续匹配使用的查询 key。

        处理规则:
            1. 去除首尾空白。
            2. 统一转为小写。
            3. 删除所有非 a-z 字符，因此数字、分隔符、标点会被移除。

        注意:
            这里做的是字符级清洗，不负责带音调拼音或特殊字符的音译转换。
            例如 ``ni4`` 会变成 ``ni``，但 ``nǐ`` 会变成 ``n``，``lü`` 会变成 ``l``。
        """
        return cls._NON_ALPHA_PATTERN.sub("", token.strip().lower())

    @classmethod
    def _split_pinyin_query(cls, pinyin: str) -> list[str]:
        """将用户输入拆分为规范化拼音 token 列表，供后续逐个匹配。"""
        if not pinyin.strip():
            return []

        return [
            normalized
            for normalized in (
                cls._normalize_pinyin_token(part) for part in cls._PINYIN_SPLIT_PATTERN.split(pinyin.strip())
            )
            if normalized
        ]

    @classmethod
    def _generate_fuzzy_variants(cls, token: str) -> list[_FuzzyVariant]:
        """生成拼音的模糊音变体，并记录变体与原始 token 的编辑距离。"""
        variants: dict[str, int] = {token: 0}

        initial = ""
        final = token
        if token.startswith(("zh", "ch", "sh")):
            initial = token[:2]
            final = token[2:]
        elif token and token[0] in "bpmfdtnlgkhjqxrzcsyw":
            initial = token[0]
            final = token[1:]

        initial_variants: list[tuple[str, int]] = [(initial, 0)]
        if initial in cls._FUZZY_INITIALS:
            initial_variants.extend((candidate, 1) for candidate in cls._FUZZY_INITIALS[initial])

        final_variants: list[tuple[str, int]] = [(final, 0)]
        for fuzzy_final, replacements in cls._FUZZY_FINALS.items():
            if final.endswith(fuzzy_final):
                prefix = final[: -len(fuzzy_final)]
                final_variants.extend((prefix + replacement, 1) for replacement in replacements)

        for init, init_edits in initial_variants:
            for fin, final_edits in final_variants:
                variant = init + fin
                edits = init_edits + final_edits
                if variant and edits < variants.get(variant, edits + 1):
                    variants[variant] = edits

        return [
            _FuzzyVariant(token=variant_token, fuzzy_edits=fuzzy_edits)
            for variant_token, fuzzy_edits in variants.items()
        ]

    def _char_frequency_score(self, char: str) -> float:
        """返回候选汉字的中文通用语料频率分数。"""
        cached_score = self._char_frequency_cache.get(char)
        if cached_score is not None:
            return cached_score

        score = zipf_frequency(char, "zh")
        self._char_frequency_cache[char] = score
        return score

    def _score_candidate(self, *, char: str, matched_key: _MatchedPinyinKey) -> float:
        """综合匹配类型与汉字频率，为单个候选字打分。"""
        return (
            self._MATCH_TYPE_SCORES[matched_key.match_type]
            + (self._char_frequency_score(char) * self._CHAR_FREQUENCY_WEIGHT)
            - (matched_key.fuzzy_edits * self._FUZZY_EDIT_PENALTY)
            - (matched_key.prefix_extra_chars * self._PREFIX_EXTRA_CHAR_PENALTY)
        )

    def _match_pinyin_keys(
        self,
        token: str,
        mapping: PinyinCharMapping,
    ) -> list[_MatchedPinyinKey]:
        """输入法风格的模糊拼音匹配。"""
        matched_keys: list[_MatchedPinyinKey] = []
        seen: set[str] = set()

        def add(match: _MatchedPinyinKey) -> None:
            if match.key not in seen:
                matched_keys.append(match)
                seen.add(match.key)

        if token in mapping:
            add(_MatchedPinyinKey(key=token, match_type="exact", fuzzy_edits=0))

        fuzzy_variants = self._generate_fuzzy_variants(token)
        for variant in fuzzy_variants[1:]:
            if variant.token in mapping:
                add(
                    _MatchedPinyinKey(
                        key=variant.token,
                        match_type="fuzzy_exact",
                        fuzzy_edits=variant.fuzzy_edits,
                    )
                )

        if not matched_keys:
            for variant in fuzzy_variants:
                for key in mapping:
                    if key.startswith(variant.token):
                        add(
                            _MatchedPinyinKey(
                                key=key,
                                match_type="prefix",
                                fuzzy_edits=variant.fuzzy_edits,
                                prefix_extra_chars=len(key) - len(variant.token),
                            )
                        )

        return matched_keys

    def _get_mapping(self, char_type: CharMatchType) -> PinyinCharMapping:
        if char_type == "char":
            return self._char_mapping
        if char_type == "surname":
            return self._surname_mapping
        raise ValueError(f"不支持的 char_type: {char_type}")

    def match_chars_by_pinyin(
        self,
        pinyin: str,
        *,
        char_type: CharMatchType = "char",
    ) -> list[str]:
        """根据拼音匹配普通汉字或姓氏候选字。"""
        mapping = self._get_mapping(char_type)
        tokens = self._split_pinyin_query(pinyin)
        if not tokens:
            return []

        ranked_candidates: dict[str, _RankedCandidate] = {}
        first_seen = 0
        for token in tokens:
            for matched_key in self._match_pinyin_keys(token, mapping):
                for char in mapping.get(matched_key.key, []):
                    first_seen += 1
                    score = self._score_candidate(char=char, matched_key=matched_key)
                    existing = ranked_candidates.get(char)
                    if existing is None or score > existing.score:
                        ranked_candidates[char] = _RankedCandidate(
                            char=char,
                            score=score,
                            first_seen=first_seen,
                        )

        return [
            candidate.char
            for candidate in sorted(
                ranked_candidates.values(),
                key=lambda candidate: (-candidate.score, candidate.first_seen),
            )
        ]

    def match_surname_chars_by_pinyin(self, pinyin: str) -> list[str]:
        """根据姓氏拼音模糊匹配候选中文姓氏字符。"""
        return self.match_chars_by_pinyin(pinyin, char_type="surname")


default_chars_matcher = CharsMatcher()


def match_chars_by_pinyin(
    pinyin: str,
    *,
    char_type: CharMatchType = "char",
) -> list[str]:
    """模块级普通汉字匹配入口。"""
    return default_chars_matcher.match_chars_by_pinyin(
        pinyin,
        char_type=char_type,
    )


def match_surname_chars_by_pinyin(pinyin: str) -> list[str]:
    """模块级姓氏拼音匹配入口。"""
    return default_chars_matcher.match_surname_chars_by_pinyin(pinyin)


__all__ = [
    "CharMatchType",
    "CharsMatcher",
    "default_chars_matcher",
    "match_chars_by_pinyin",
    "match_surname_chars_by_pinyin",
]
