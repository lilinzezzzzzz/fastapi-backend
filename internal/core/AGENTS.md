# AGENTS.md

适用于 `internal/core/`。

## 层职责

本层承载应用级错误类型、错误码、异常封装和核心横切定义。

## 编码约定

- 错误码、错误语义和异常 envelope 属于 API contract，保持稳定。
- 新增业务错误优先在现有错误体系中扩展，不要在 Controller 或 Service 中临时拼接错误结构。
- 异常类保持轻量，避免依赖数据库、Redis、HTTP client 或业务 Service。
- 错误消息要可排障，但不要包含 secret、token、密码、连接串或第三方凭证。

## 兼容性要求

- 修改错误码、HTTP 状态映射或响应结构前，检查 API 测试、中间件和前端/外部调用方兼容性。
- 删除旧错误定义前确认没有历史接口、任务或 SDK 依赖。

## 验证重点

- 错误转换、中间件捕获、FastAPI validation error 行为。
- 认证、参数校验、业务异常和未预期异常的响应结构。
