from __future__ import annotations

import json
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import opencc
from pypinyin import Style, lazy_pinyin, pinyin
from wordfreq import zipf_frequency

CHARS_MATCHER_DIR = Path(__file__).resolve().parents[1]
CHARS_DIR = CHARS_MATCHER_DIR / "chars"
PINYIN_DIR = CHARS_DIR / "pinyin"
PINYIN_MAPPING_PATH = PINYIN_DIR / "pinyin_chars.json"
SURNAME_MAPPING_PATH = PINYIN_DIR / "surname_pinyin_chars.json"
NON_CANONICAL_AUTO_FREQUENCY_THRESHOLD = 4.0
UMLAUT_TRANSLATION = str.maketrans(
    {
        "ü": "v",
        "ǖ": "v",
        "ǘ": "v",
        "ǚ": "v",
        "ǜ": "v",
    }
)
_T2S_CONVERTER = opencc.OpenCC("t2s")

# Keep a small curated set of common non-canonical readings that are
# genuinely useful in personal names or surnames. High-frequency function
# characters otherwise keep only their canonical reading to avoid noisy
# historical or phrase-only readings such as "说 -> yue".
POLYPHONIC_NAME_OVERRIDES: dict[str, tuple[str, ...]] = {
    "乐": ("yue",),
    "曾": ("zeng",),
    "区": ("ou",),
    "秘": ("bi",),
    "薄": ("bo", "bu"),
    "折": ("she",),
    "种": ("chong",),
    "仇": ("qiu",),
    "缪": ("miao", "miu"),
    "朴": ("piao", "po"),
    "解": ("xie",),
    "单": ("shan",),
    "查": ("zha",),
    "翟": ("zhai",),
    "覃": ("qin",),
    "沈": ("chen",),
    "尉": ("yu",),
    "长": ("zhang",),
    "重": ("chong",),
    "行": ("hang",),
    "柏": ("bo",),
    "盖": ("ge",),
    "藏": ("zang",),
    "员": ("yun",),
}

def load_mapping(path: Path) -> dict[str, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")

    normalized: dict[str, list[str]] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, list):
            raise ValueError(f"{path} must contain dict[str, list[str]]")
        normalized[key] = [item for item in value if isinstance(item, str) and item]
    return normalized


def normalize_pinyin_token(token: str) -> str:
    normalized = token.strip().lower().replace("u:", "v").replace("u：", "v")
    normalized = normalized.translate(UMLAUT_TRANSLATION)
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return "".join(char for char in normalized if "a" <= char <= "z")


@lru_cache(maxsize=None)
def is_simplified_name_char(char: str) -> bool:
    """保留简体字和简繁同形字，过滤可直接映射到其他简体字的繁体候选。"""
    return _T2S_CONVERTER.convert(char) == char


@lru_cache(maxsize=None)
def char_frequency(char: str) -> float:
    return zipf_frequency(char, "zh")


@lru_cache(maxsize=None)
def canonical_pinyin(char: str) -> str:
    tokens = lazy_pinyin(char, errors="default")
    if not tokens:
        return ""
    return normalize_pinyin_token(tokens[0])


@lru_cache(maxsize=None)
def heteronym_tokens(char: str) -> tuple[str, ...]:
    raw_tokens = pinyin(
        char,
        style=Style.NORMAL,
        heteronym=True,
        errors="default",
        strict=False,
    )[0]
    seen: set[str] = set()
    normalized_tokens: list[str] = []
    for token in raw_tokens:
        normalized = normalize_pinyin_token(token)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_tokens.append(normalized)
    return tuple(normalized_tokens)


def write_mapping(path: Path, mapping: dict[str, list[str]]) -> None:
    items = list(mapping.items())
    lines = ["{"]
    for index, (key, values) in enumerate(items):
        suffix = "," if index < len(items) - 1 else ""
        key_json = json.dumps(key, ensure_ascii=False, separators=(",", ":"))
        value_json = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
        lines.append(f"{key_json}:{value_json}{suffix}")
    lines.append("}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def iter_unique_single_chars(mapping: dict[str, list[str]]) -> list[str]:
    ordered_chars: list[str] = []
    seen: set[str] = set()
    for values in mapping.values():
        for value in values:
            if len(value) != 1 or value in seen:
                continue
            seen.add(value)
            ordered_chars.append(value)
    return ordered_chars


def rebuild_name_mapping(current_mapping: dict[str, list[str]]) -> dict[str, list[str]]:
    ordered_chars = [
        char
        for char in iter_unique_single_chars(current_mapping)
        if is_simplified_name_char(char)
    ]
    original_index = {char: index for index, char in enumerate(ordered_chars)}
    bucketed_chars: dict[str, list[str]] = defaultdict(list)

    for char in ordered_chars:
        # 如果字在 POLYPHONIC_NAME_OVERRIDES 中有配置，则只使用配置中的拼音
        override_tokens = POLYPHONIC_NAME_OVERRIDES.get(char)
        if override_tokens:
            tokens = list(override_tokens)
        else:
            canonical_token = canonical_pinyin(char)
            tokens = [canonical_token]

            if (
                char_frequency(char) <= NON_CANONICAL_AUTO_FREQUENCY_THRESHOLD
            ):
                for token in heteronym_tokens(char):
                    if token not in tokens:
                        tokens.append(token)

        for token in tokens:
            bucketed_chars[token].append(char)

    ordered_keys = list(current_mapping)
    ordered_keys.extend(sorted(set(bucketed_chars) - set(current_mapping)))

    rebuilt: dict[str, list[str]] = {}
    for key in ordered_keys:
        values = bucketed_chars.get(key)
        if not values:
            continue
        values.sort(
            key=lambda char: (
                0 if canonical_pinyin(char) == key else 1,
                -char_frequency(char),
                original_index[char],
                char,
            )
        )
        rebuilt[key] = values
    return rebuilt


def rebuild_surname_mapping(
    current_mapping: dict[str, list[str]],
) -> dict[str, list[str]]:
    rebuilt: dict[str, list[str]] = {}

    for key, raw_values in current_mapping.items():
        values: list[str] = []
        seen: set[str] = set()
        for value in raw_values:
            if value in seen:
                continue
            seen.add(value)
            values.append(value)

        rebuilt[key] = values

    return rebuilt


def main() -> None:
    current_name_mapping = load_mapping(PINYIN_MAPPING_PATH)
    current_surname_mapping = load_mapping(SURNAME_MAPPING_PATH)

    rebuilt_name_mapping = rebuild_name_mapping(current_name_mapping)
    rebuilt_surname_mapping = rebuild_surname_mapping(current_surname_mapping)

    write_mapping(PINYIN_MAPPING_PATH, rebuilt_name_mapping)
    write_mapping(SURNAME_MAPPING_PATH, rebuilt_surname_mapping)

    print(
        "rebuilt",
        PINYIN_MAPPING_PATH,
        len(rebuilt_name_mapping),
        "keys",
        sum(len(values) for values in rebuilt_name_mapping.values()),
        "values",
    )
    print(
        "rebuilt",
        SURNAME_MAPPING_PATH,
        len(rebuilt_surname_mapping),
        "keys",
        sum(len(values) for values in rebuilt_surname_mapping.values()),
        "values",
    )


if __name__ == "__main__":
    main()
