from __future__ import annotations

import sys
import types


database_module = types.ModuleType("internal.infra.database")
database_module.reset_async_db = lambda: None

redis_module = types.ModuleType("internal.infra.redis")
redis_module.reset_async_redis = lambda: None

infra_module = types.ModuleType("internal.infra")
infra_module.database = database_module
infra_module.redis = redis_module

sys.modules["internal.infra"] = infra_module
sys.modules["internal.infra.database"] = database_module
sys.modules["internal.infra.redis"] = redis_module
