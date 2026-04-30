"""中文候选字拼音和字形匹配 package。

异步预加载
-----------
为避免首次请求时的加载延迟，建议在应用启动时预加载：

    from pkg.chars_matcher import preload

    async def lifespan(app: FastAPI):
        await preload()  # 并行加载拼音和字形数据
        yield
"""

from pkg.chars_matcher.matcher import (
    CharMatchType,
    CharsMatcher,
    default_chars_matcher,
    preload,
)
from pkg.chars_matcher.pinyin_chars_matcher import PinyinCharsMatcher
from pkg.chars_matcher.shape_chars_matcher import ShapeCharsMatcher

__all__ = [
    "CharMatchType",
    "CharsMatcher",
    "PinyinCharsMatcher",
    "ShapeCharsMatcher",
    "default_chars_matcher",
    "preload",
]
