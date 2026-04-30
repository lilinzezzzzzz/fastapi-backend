"""chars matcher 输入校验工具。"""

from __future__ import annotations

_HAN_CODEPOINT_RANGES: tuple[tuple[int, int], ...] = (
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0x20000, 0x2A6DF),  # CJK Unified Ideographs Extension B
    (0x2A700, 0x2B73F),  # CJK Unified Ideographs Extension C
    (0x2B740, 0x2B81F),  # CJK Unified Ideographs Extension D
    (0x2B820, 0x2CEAF),  # CJK Unified Ideographs Extension E
    (0x2CEB0, 0x2EBEF),  # CJK Unified Ideographs Extension F
    (0x2F800, 0x2FA1F),  # CJK Compatibility Ideographs Supplement
    (0x30000, 0x3134F),  # CJK Unified Ideographs Extension G
    (0x31350, 0x323AF),  # CJK Unified Ideographs Extension H
)


def is_han_char(char: str) -> bool:
    """判断字符是否为单个汉字。"""
    if len(char) != 1:
        return False

    codepoint = ord(char)
    return any(start <= codepoint <= end for start, end in _HAN_CODEPOINT_RANGES)


def is_han_text(text: str) -> bool:
    """判断文本是否全部由汉字组成。"""
    return bool(text) and all(is_han_char(char) for char in text)


def normalize_single_han_char(text: str, *, matcher_name: str) -> str:
    """规范化并校验单个汉字查询。"""
    normalized_text = text.strip()
    if not normalized_text:
        return ""
    if len(normalized_text) != 1:
        raise ValueError(f"{matcher_name} 只支持单个汉字查询")
    if not is_han_char(normalized_text):
        raise ValueError(f"{matcher_name} 只支持单个汉字查询，且输入必须为汉字")
    return normalized_text


__all__ = ["is_han_char", "is_han_text", "normalize_single_han_char"]
