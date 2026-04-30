# AGENTS.md

适用于 `pkg/database/`。

## 层职责

本目录提供 SQLAlchemy async 基础设施、模型 Mixin、DAO 基类、查询构建器和数据库类型封装。

## 编码约定

- 保持 SQLAlchemy 2.x typed API 风格。
- DAO、builder、session provider 是共享基础设施，变更前全仓检索调用方。
- 查询构建器应组合 SQL 表达式，不应掺入业务字段假设。
- 类型封装要兼容当前支持的 MySQL、PostgreSQL、Oracle，以及测试中的 SQLite。
- 公共 API 变更要保持向后兼容或明确迁移路径。

## 数据库约束

通用数据库硬约束（禁循环内 ORM 调用、批量优先、不吞异常）见全局 `~/.qoder/AGENTS.md` Database / Performance 章节。本包特有约束：

- 批量操作应提供明确的批量接口，不鼓励调用方逐条执行。

## 验证重点

- 运行 ORM 和数据库类型相关测试，例如 `tests/orm/`、`tests/test_json_type.py`。
- builder 或 DAO 基类变更还要运行依赖 `BaseDao` 的业务 DAO 测试。
