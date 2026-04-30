"""chars matcher 对外组合入口。

模块概述
=========
本模块提供统一的汉字候选匹配 API，组合了拼音匹配和字形匹配两种策略。

支持的匹配模式
-------------
1. **拼音匹配** (match_chars_by_pinyin)
   - 输入法风格模糊匹配
   - 支持声母/韵母模糊、前缀匹配
   - 适用于用户知道拼音但可能输入不精确的场景

2. **混合匹配** (match_chars_by_mix)
   - 先拼音匹配产生候选池
   - 对候选按字形相似度排序，取 top-N 前置
   - 其余候选保持拼音原序
   - 适用于 ASR 姓名场景

使用方式
---------
使用默认单例::

    from pkg.chars_matcher import default_chars_matcher
    candidates = default_chars_matcher.match_chars_by_mix("李", pinyin="li")
"""

from __future__ import annotations

import anyio

from pkg.chars_matcher.pinyin_chars_matcher import PinyinCharsMatcher
from pkg.chars_matcher.shape_chars_matcher import ShapeCharsMatcher
from pkg.chars_matcher.types import CharMatchType
from pkg.chars_matcher.validation import is_han_text, normalize_single_han_char

_SHAPE_BOOST_TOP_N = 3


class CharsMatcher:
    """组合字形与拼音 matcher，对外暴露统一 API。

    该类将拼音匹配器和字形匹配器组合在一起，提供统一的接口。
    支持单独使用拼音或字形匹配，也支持混合匹配。

    Args:
        pinyin_chars_matcher: 自定义拼音匹配器实例,默认使用标准配置
        shape_chars_matcher: 自定义字形匹配器实例，默认使用标准配置

    Example:
        >>> matcher = CharsMatcher()
        >>> matcher.match_chars_by_pinyin("li")
        ['李', '理', '里', ...]
        >>> matcher.match_chars_by_mix("李", pinyin="li")
        ['李', '季', '杏', '理', ...]
    """

    def __init__(
        self,
        *,
        pinyin_chars_matcher: PinyinCharsMatcher | None = None,
        shape_chars_matcher: ShapeCharsMatcher | None = None,
    ) -> None:
        self._pinyin_chars_matcher = pinyin_chars_matcher or PinyinCharsMatcher()
        self._shape_chars_matcher = shape_chars_matcher or ShapeCharsMatcher()

    @staticmethod
    def _normalize_text_for_char_type(
        text: str,
        *,
        char_type: CharMatchType,
        matcher_name: str,
    ) -> str:
        normalized_text = text.strip()
        if not normalized_text:
            return ""
        if char_type == "char":
            return normalize_single_han_char(normalized_text, matcher_name=matcher_name)
        if char_type == "surname":
            if len(normalized_text) > 2:
                raise ValueError(f"{matcher_name} 只支持 1 到 2 个汉字姓氏查询")
            if not is_han_text(normalized_text):
                raise ValueError(f"{matcher_name} 只支持 1 到 2 个汉字姓氏查询")
            return normalized_text
        raise ValueError(f"不支持的 char_type: {char_type}")

    async def preload(self) -> None:
        """异步预加载所有匹配器数据与排序依赖，避免首次请求时的阻塞。

        并行加载拼音和字形数据，避免首个请求触发懒加载。

        建议在应用启动时调用，例如：

            from pkg.chars_matcher import default_chars_matcher

            async def lifespan(app: FastAPI):
                await default_chars_matcher.preload()
                yield

        多次调用是安全的，后续调用会立即返回。
        """
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._pinyin_chars_matcher.preload)
            tg.start_soon(self._shape_chars_matcher.preload)

    def match_chars_by_pinyin(
        self,
        pinyin: str,
        *,
        char_type: CharMatchType = "char",
        query_text: str | None = None,
    ) -> list[str]:
        """根据拼音匹配普通汉字或姓氏候选字。

        ✅ **支持多字输入**：拼音可通过空格/逗号分隔多个 token（如 "li ming"）。

        Args:
            pinyin: 用户输入的拼音（支持多 token，如 "li" 或 "li ming"）
            char_type: "char" 普通汉字，"surname" 姓氏
            query_text: 原始查询文本，用于精确匹配加权

        Returns:
            排序后的候选字列表
        """
        return self._pinyin_chars_matcher.match_chars_by_pinyin(
            pinyin,
            char_type=char_type,
            query_text=query_text,
        )

    def resolve_text_to_pinyin(
        self,
        text: str,
        *,
        char_type: CharMatchType = "char",
    ) -> str:
        """返回文本在当前匹配上下文中的首选展示拼音。"""
        normalized_text = self._normalize_text_for_char_type(
            text,
            char_type=char_type,
            matcher_name="chars matcher",
        )
        if not normalized_text:
            return ""
        return self._pinyin_chars_matcher.preferred_text_pinyin_key(
            normalized_text,
            char_type=char_type,
        )

    def _match_single_char_with_shape_boost(
        self,
        text: str,
        *,
        pinyin_candidates: list[str],
    ) -> list[str]:
        """单字候选融合策略：shape top-N 前置，其余保持拼音原序。

        管道流程：
        1. 用 heapq.nsmallest 从拼音候选中取字形最相似的前 N 个
        2. 原字始终置顶，shape boost 紧随其后
        3. 剩余候选保持拼音匹配器的原始排序
        """
        shape_top = self._shape_chars_matcher.top_n_by_shape(
            text,
            candidates=pinyin_candidates,
            n=_SHAPE_BOOST_TOP_N,
        )
        # 合并：原字 > shape top-N > 剩余拼音候选（保持原序）
        boosted: set[str] = set(shape_top)
        boosted.add(text)
        result = [text]
        result.extend(shape_top)
        result.extend(char for char in pinyin_candidates if char not in boosted)
        return result

    def match_surname_chars_by_text(self, text: str) -> list[str]:
        """根据中文姓氏文本返回候选姓氏。

        匹配策略：
        - 单字姓（len==1）：先拼音匹配，再按字形相似度重排
        - 多字姓（len==2）：只走 surname pinyin
        """
        normalized_text = self._normalize_text_for_char_type(
            text,
            char_type="surname",
            matcher_name="surname matcher",
        )
        if not normalized_text:
            return []

        # 单字姓：shape + pinyin 合并匹配
        if len(normalized_text) == 1:
            pinyin_candidates = self._pinyin_chars_matcher.match_surname_chars_by_text(normalized_text)
            return self._match_single_char_with_shape_boost(
                normalized_text,
                pinyin_candidates=pinyin_candidates,
            )

        # 多字姓：只走拼音匹配
        return self._pinyin_chars_matcher.match_surname_chars_by_text(normalized_text)

    def match_chars_by_mix(
        self,
        text: str,
        *,
        pinyin: str | None = None,
    ) -> list[str]:
        """先拼音匹配，再用字形相似度 boost 前置，返回单字候选。

        ⚠️ **限制**：仅支持单个汉字输入，不支持多字查询。

        匹配策略：
        1. 原字本身始终排在第一位
        2. 拼音候选作为完整候选池
        3. 对拼音候选按字形相似度排序，取 top-N 前置
        4. 其余候选保持拼音匹配器的原始排序

        适用场景：
        - ASR 姓名输入补全
        - 已知中文文本，想在同音候选里优先返回更像的字

        Args:
            text: 单个汉字查询（如 "李"）
            pinyin: 可选拼音，用于拼音匹配补充；若未提供则自动转换

        Returns:
            去重后的候选字列表（按字形相似度排序）

        Raises:
            ValueError: 输入不是单个汉字
        """
        normalized_text = normalize_single_han_char(text, matcher_name="mix matcher")
        if not normalized_text:
            return []

        resolved_pinyin = pinyin.strip() if pinyin is not None else ""
        if resolved_pinyin:
            pinyin_candidates = self._pinyin_chars_matcher.match_chars_by_pinyin(
                resolved_pinyin,
                query_text=normalized_text,
            )
        else:
            pinyin_candidates = self._pinyin_chars_matcher.match_chars_by_text(
                normalized_text,
                char_type="char",
            )
        return self._match_single_char_with_shape_boost(
            normalized_text,
            pinyin_candidates=pinyin_candidates,
        )


# 默认全局单例，供模块级函数使用
default_chars_matcher = CharsMatcher()


async def preload() -> None:
    """模块级异步预加载入口。

    预加载默认单例的所有数据，避免首次请求时的阻塞。

    建议在应用启动时调用：

        from pkg.chars_matcher import preload

        async def lifespan(app: FastAPI):
            await preload()
            yield

    或者直接使用默认单例：

        from pkg.chars_matcher import default_chars_matcher
        await default_chars_matcher.preload()
    """
    await default_chars_matcher.preload()


__all__ = [
    "CharMatchType",
    "CharsMatcher",
    "default_chars_matcher",
    "preload",
]
