"""中文候选字拼音匹配 package。"""

from pkg.chars_matcher.matcher import (
    CharMatchType,
    CharsMatcher,
    default_chars_matcher,
    match_chars_by_pinyin,
    match_surname_chars_by_pinyin,
)

__all__ = [
    "CharMatchType",
    "CharsMatcher",
    "default_chars_matcher",
    "match_chars_by_pinyin",
    "match_surname_chars_by_pinyin",
]
