"""配置模块"""

from internal.config.loader import get_settings, init_settings
from internal.config.settings import Settings
from pkg.toolkit.types import lazy_proxy

# 使用 lazy_proxy 创建延迟加载的配置实例，类型推断为 Settings
settings = lazy_proxy(get_settings)

__all__ = ["settings", "init_settings", "get_settings"]
