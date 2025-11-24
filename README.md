# 项目结构说明

这是一套基于 **FastAPI** 的后端服务，采用清晰的分层架构。整体结构将业务逻辑、接口适配、基础设施进行解耦，便于扩展、测试与维护。下面按模块进行说明。

---

## internal/ —— 核心业务模块

### controllers/ — 请求处理层
负责接收和解析 HTTP 请求，调用业务服务并返回响应。通常按业务子域拆分，例如用户、订单、权限等。

- `web/` — 面向前端的接口
- `publicapi/` — 对外公开的 API（如开放平台接口）
- `internalapi/` — 后端内部系统间调用接口
- `serviceapi/` — 微服务之间的 RPC/REST 调用接口

### services/ — 业务逻辑层  
封装具体业务规则，比如用户注册、登录、权限校验等。controller 不做业务逻辑，统一交给 service 处理。

### dao/ — 数据访问层  
数据库操作层，负责 SQL/ORM 逻辑，与 service 解耦。通常由 Repository 模式实现。

### models/ — ORM 模型（SQLAlchemy）
数据库实体模型的定义，用于持久化操作。

### schemas/ — 数据校验模型（Pydantic）
请求/响应的数据结构，用于输入校验和输出规范。

### core/ — 核心功能模块
放置跨领域但高内聚的核心能力，例如：

- Token 与认证处理
- 通用异常与错误码
- 配置加载
- 全局依赖注入方法

### middleware/ — 中间件  
在请求进入 controller 前执行：

- 鉴权与令牌解析
- 日志记录
- 路由追踪等

### infra/ — 基础设施适配层  
对外部系统进行封装，例如：

- 数据库连接管理（SQLAlchemy Session）
- Redis、消息队列、对象存储等适配器
- 对外 API 客户端实现

### utils/ — 工具函数  
通用的非业务工具函数，如时间处理、加密、格式转换等。

### aps_tasks/ — 定时任务（APScheduler）  
用于实现周期性任务，例如清理缓存、数据同步等。

### celery_tasks/ — 异步任务（Celery）  
异步执行队列任务，如发邮件、生成文件等。

---

## pkg/ —— 工具库（独立可复用）
项目包含约 **18 个通用工具模块**，可单独作为内部 SDK 使用，主要包括：

- ORM 封装
- JWT 工具
- 加密与签名
- 日志组件
- Celery / APScheduler 管理器
- HTTP 客户端封装
- gRPC 客户端工具
- OpenAI SDK 包装器  
等多个可复用能力模块。

---

## 配置与部署

### configs/
存放不同环境（dev/staging/prod）的配置文件。

### Dockerfile
项目的容器化构建配置。

### scripts/
项目工具脚本，例如创建数据库、初始化环境、启动脚本等。

### tests/
测试用例与集成测试。

---

## 请求流程说明

```

前端 → middleware → controller → service → dao → 数据库
↓                               ↑
（回传数据） ← service ← controller ← transformers → 前端

```

流程解读：

1. 前端发起请求  
2. middleware 处理鉴权、日志等  
3. controller 解析参数，调用对应 service  
4. service 执行业务逻辑  
5. dao 操作数据库  
6. service 整理结果返回 controller  
7. controller 将结果交给 transformers（序列化/格式化）  
8. 前端接收响应
PYTHONUNBUFFERED=1;PYTHONIOENCODING=utf-8;APP_ENV=local
---
