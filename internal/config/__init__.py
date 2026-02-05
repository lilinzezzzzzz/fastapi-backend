"""配置模块"""

from internal.config.loader import get_settings, init_settings
from internal.config.settings import Settings
from pkg.toolkit.types import LazyProxy

# 使用 LazyProxy 包装配置实例，提供延迟加载和类型提示
settings: LazyProxy[Settings] = LazyProxy(get_settings)

__all__ = ["settings", "init_settings", "get_settings"]
