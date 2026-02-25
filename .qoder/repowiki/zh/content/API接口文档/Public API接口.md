# Public API接口

<cite>
**本文档引用的文件**
- [internal/controllers/publicapi/__init__.py](file://internal/controllers/publicapi/__init__.py)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py)
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py)
- [internal/app.py](file://internal/app.py)
- [main.py](file://main.py)
- [internal/core/exception.py](file://internal/core/exception.py)
- [pkg/toolkit/response.py](file://pkg/toolkit/response.py)
- [internal/utils/signature.py](file://internal/utils/signature.py)
- [pkg/toolkit/signature.py](file://pkg/toolkit/signature.py)
- [internal/core/auth.py](file://internal/core/auth.py)
</cite>

## 更新摘要
**变更内容**
- 新增验证错误测试能力，包含Pydantic模型验证和错误处理
- 扩展测试接口范围，新增验证错误测试接口
- 完善请求模式定义，支持POST请求的JSON验证
- 增强中间件对验证错误的统一处理机制

## 目录
1. [简介](#简介)
2. [项目结构](#项目结构)
3. [核心组件](#核心组件)
4. [架构总览](#架构总览)
5. [详细组件分析](#详细组件分析)
6. [依赖关系分析](#依赖关系分析)
7. [性能考量](#性能考量)
8. [故障排查指南](#故障排查指南)
9. [结论](#结论)
10. [附录](#附录)

## 简介
本文件面向第三方开发者，系统性梳理并说明 Public API（公开接口）的设计原则、安全机制、稳定性保障与可维护性策略。Public API 采用统一的路由前缀与认证策略，结合中间件链路实现请求拦截、日志记录、异常处理与响应标准化。本文档同时给出接口规范、使用示例、SDK集成建议、版本管理与废弃策略，以及API文档生成与在线测试的配置说明。

**更新** 新增验证错误测试能力，支持Pydantic模型验证和统一错误处理机制。

## 项目结构
Public API 的路由组织位于公共控制器模块中，通过统一的 APIRouter 注册到应用生命周期内。认证与日志中间件贯穿请求处理链路，确保安全性与可观测性。

```mermaid
graph TB
A["应用入口<br/>main.py"] --> B["应用工厂<br/>internal/app.py"]
B --> C["注册路由<br/>include_router(...)"]
C --> D["Public API 路由前缀<br/>/v1/public"]
D --> E["Public API 子路由<br/>test.py"]
E --> F["验证错误测试接口<br/>/test/test_validation_error"]
B --> G["中间件注册<br/>GZip/CORS/记录/认证"]
G --> H["认证中间件<br/>ASGIAuthMiddleware"]
G --> I["记录中间件<br/>ASGIRecordMiddleware"]
```

**图表来源**
- [main.py](file://main.py#L1-L18)
- [internal/app.py](file://internal/app.py#L33-L45)
- [internal/controllers/publicapi/__init__.py](file://internal/controllers/publicapi/__init__.py#L4-L11)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L88-L149)
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py#L66-L122)

**章节来源**
- [internal/controllers/publicapi/__init__.py](file://internal/controllers/publicapi/__init__.py#L1-L12)
- [internal/app.py](file://internal/app.py#L33-L45)

## 核心组件
- 路由与前缀
  - Public API 路由前缀为 /v1/public，所有公开接口在此命名空间下注册。
- 认证与白名单
  - 认证中间件支持三类路径判定：白名单放行、内部接口签名校验、普通接口 Token 校验。
  - Public API 路径属于白名单范畴，无需 Token 即可访问。
  - **新增** 测试路径 /test 也属于白名单，便于联调和验证错误测试。
- 日志与追踪
  - 记录中间件自动注入 X-Process-Time 与 X-Trace-ID 响应头，便于问题定位与性能分析。
- 异常与响应
  - 统一异常体系与响应体结构，确保错误信息与国际化文案一致。
  - **新增** 验证错误通过 RequestValidationError 统一处理，返回标准错误响应。
- 文档与调试
  - Debug 模式下启用 /docs 与 /redoc，在线交互式文档便于联调与测试。

**章节来源**
- [internal/controllers/publicapi/__init__.py](file://internal/controllers/publicapi/__init__.py#L4-L11)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L13-L46)
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py#L15-L42)
- [internal/app.py](file://internal/app.py#L19-L24)
- [pkg/toolkit/response.py](file://pkg/toolkit/response.py#L47-L81)
- [internal/core/exception.py](file://internal/core/exception.py#L19-L37)

## 架构总览
Public API 的请求处理链路如下：

```mermaid
sequenceDiagram
participant Client as "客户端"
participant App as "FastAPI 应用"
participant Recorder as "记录中间件"
participant Auth as "认证中间件"
participant Router as "Public API 路由"
participant Handler as "视图函数"
Client->>App : "HTTP 请求"
App->>Recorder : "进入记录中间件"
Recorder->>Recorder : "初始化上下文/注入追踪头"
Recorder->>Auth : "进入认证中间件"
Auth->>Auth : "判定路径类型/白名单放行"
Auth-->>Recorder : "放行或校验通过"
Recorder->>Router : "路由分发"
Router->>Handler : "调用具体处理函数"
alt 验证错误
Handler-->>Router : "抛出 RequestValidationError"
Router-->>Recorder : "重新抛出异常"
Recorder->>Recorder : "统一处理验证错误"
Recorder-->>Client : "返回标准错误响应"
else 正常处理
Handler-->>Router : "返回响应"
Router-->>Recorder : "返回响应"
Recorder-->>Client : "带追踪头的响应"
end
```

**图表来源**
- [internal/app.py](file://internal/app.py#L55-L81)
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py#L70-L102)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L88-L118)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L12-L19)

## 详细组件分析

### Public API 路由与前缀
- 路由前缀：/v1/public
- 子路由注册：通过 include_router 将 test 子路由挂载到公共前缀下
- 特点：清晰的版本化命名空间，便于后续演进与废弃策略实施

**章节来源**
- [internal/controllers/publicapi/__init__.py](file://internal/controllers/publicapi/__init__.py#L4-L11)

### 认证中间件（白名单与签名）
- 白名单路径判定
  - Public API 路径前缀 /v1/public 属于白名单，无需 Token 即可访问
  - **新增** 测试路径 /test 也属于白名单，便于联调和验证错误测试
  - 其他固定路径（如登录、OpenAPI）同样白名单放行
- 内部接口签名校验
  - 内部接口前缀 /v1/internal 需要签名头：X-Signature、X-Timestamp、X-Nonce
  - 使用 HMAC+密钥进行签名校验，支持时间戳容忍度，防止重放攻击
- Token 校验
  - 普通接口需携带 Authorization 或等效头，内部通过 verify_token 校验
  - 校验通过后将用户上下文写入全局上下文，便于审计与日志追踪

```mermaid
flowchart TD
Start(["请求进入"]) --> PathCheck["判定路径类型"]
PathCheck --> IsPublic{"是否 Public API 路径？"}
IsPublic --> |是| Whitelist["白名单放行"]
IsPublic --> |否| IsTest{"是否测试路径？"}
IsTest --> |是| Whitelist
IsTest --> |否| IsInternal{"是否 Internal API 路径？"}
IsInternal --> |是| VerifySig["校验签名头<br/>X-Signature/X-Timestamp/X-Nonce"]
VerifySig --> SigOK{"签名有效？"}
SigOK --> |否| Deny["拒绝访问"]
SigOK --> |是| Next["继续处理"]
IsInternal --> |否| VerifyToken["校验 Token"]
VerifyToken --> TokenOK{"Token 有效？"}
TokenOK --> |否| Deny
TokenOK --> |是| Next
Whitelist --> Next
Next --> End(["进入路由处理"])
```

**图表来源**
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L57-L63)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L119-L131)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L132-L149)

**章节来源**
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L13-L46)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L88-L149)
- [internal/utils/signature.py](file://internal/utils/signature.py#L9-L26)
- [pkg/toolkit/signature.py](file://pkg/toolkit/signature.py#L9-L26)
- [internal/core/auth.py](file://internal/core/auth.py#L4-L18)

### 记录中间件（日志与追踪）
- 上下文初始化
  - 以请求头中的 X-Trace-ID 作为追踪 ID，若无则生成新的 UUID v6 字符串
- 响应头注入
  - 注入 X-Process-Time（处理耗时）与 X-Trace-ID（追踪 ID）
- 异常处理
  - 区分业务异常与系统异常，分别记录 warning 与 error
  - **新增** 验证错误统一处理，返回标准错误响应
  - 若尚未开始响应，构造统一错误响应；若响应已开始，则记录严重告警

**章节来源**
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py#L15-L42)
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py#L66-L122)

### 异常与响应标准化
- 统一异常
  - AppException 支持任意错误码与消息，配合 GlobalErrors 提供中英文文案
- 统一响应体
  - _ResponseBody 结构包含 code、message、data
  - CustomORJSONResponse 基于 orjson 高性能序列化，确保一致性
- 错误响应工厂
  - error_response/error 支持多语言文案拼接与错误码映射
- **新增** 验证错误处理
  - RequestValidationError 通过中间件统一捕获和处理
  - 返回标准错误响应，包含详细的验证错误信息

**章节来源**
- [internal/core/exception.py](file://internal/core/exception.py#L4-L37)
- [pkg/toolkit/response.py](file://pkg/toolkit/response.py#L47-L81)
- [pkg/toolkit/response.py](file://pkg/toolkit/response.py#L88-L170)
- [pkg/toolkit/response.py](file://pkg/toolkit/response.py#L195-L200)

### Public API 示例接口
- **新增** 验证错误测试
  - POST /v1/public/test/test_validation_error：测试请求验证异常，使用Pydantic模型进行参数验证
  - 支持的验证规则：name长度2-20字符、age范围0-150、email格式验证
- 测试异常
  - GET /v1/public/test/test_raise_exception：触发系统异常，由中间件捕获并返回统一错误响应
  - GET /v1/public/test/test_raise_app_exception：触发业务异常，返回统一错误响应
- 上下文与任务
  - GET /v1/public/test/test_contextvars_on_asyncio_task：在异步任务中传递 trace_id 上下文
- 事件流（SSE）
  - GET /v1/public/test/test/sse-stream：逐步返回文本片段，演示 SSE 基本用法
  - GET /v1/public/chat/sse-stream/timeout：按块超时控制的 SSE 流，结合装饰器 stream_with_chunk_control

**章节来源**
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L15-L24)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L25-L36)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L33-L36)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L47-L75)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L84-L89)

### 验证错误测试能力
- **新增** Pydantic模型验证
  - TestValidationRequest 模型定义了严格的参数验证规则
  - 支持字符串长度、数值范围、正则表达式等多种验证方式
- **新增** 统一错误处理
  - 验证失败时抛出 RequestValidationError
  - 中间件捕获并转换为标准错误响应
  - 返回详细的错误信息，便于前端处理和用户反馈

**章节来源**
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L17-L22)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L26-L36)
- [internal/app.py](file://internal/app.py#L47-L50)
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py#L100-L101)

## 依赖关系分析
Public API 的运行依赖于应用生命周期初始化与中间件链路，各组件耦合度低、职责清晰。

```mermaid
graph TB
subgraph "应用层"
M["main.py"]
A["internal/app.py"]
end
subgraph "中间件层"
R["ASGIRecordMiddleware<br/>记录中间件"]
T["ASGIAuthMiddleware<br/>认证中间件"]
end
subgraph "公共API层"
P["/v1/public<br/>publicapi/__init__.py"]
S["test.py<br/>示例接口"]
V["TestValidationRequest<br/>验证模型"]
end
subgraph "基础设施"
I["init_signature_auth_handler"]
SIG["SignatureAuthHandler"]
end
M --> A
A --> R
A --> T
A --> P
P --> S
S --> V
I --> SIG
T --> SIG
```

**图表来源**
- [main.py](file://main.py#L1-L18)
- [internal/app.py](file://internal/app.py#L55-L81)
- [internal/controllers/publicapi/__init__.py](file://internal/controllers/publicapi/__init__.py#L4-L11)
- [internal/utils/signature.py](file://internal/utils/signature.py#L9-L26)
- [pkg/toolkit/signature.py](file://pkg/toolkit/signature.py#L9-L26)

**章节来源**
- [internal/app.py](file://internal/app.py#L84-L108)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L88-L149)

## 性能考量
- 压缩传输
  - 启用 GZip 中间件，降低网络传输体积，提升吞吐
- 高性能序列化
  - 使用 orjson 进行 JSON 序列化，减少 CPU 开销
- 超时与流控
  - SSE 场景可通过装饰器对块级超时进行控制，避免长时间占用连接
- 日志与追踪
  - 记录中间件提供 X-Process-Time 与 X-Trace-ID，便于性能分析与问题定位
- **新增** 验证错误处理性能
  - 验证错误通过中间件统一处理，避免重复代码和性能损耗

**章节来源**
- [internal/app.py](file://internal/app.py#L57-L59)
- [pkg/toolkit/response.py](file://pkg/toolkit/response.py#L62-L81)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L84-L89)
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py#L54-L63)

## 故障排查指南
- 常见错误与定位
  - 业务异常：记录为 warning，查看日志中的业务异常堆栈
  - 系统异常：记录为 error，查看日志中的系统异常堆栈
  - **新增** 验证错误：查看详细的验证错误信息，确认参数格式是否符合要求
  - 响应已开始：若响应头已发送，将无法再返回错误响应，记录为 critical 并附带 trace_id
- 认证相关
  - Public API 无需 Token，若出现 401/403，请确认请求路径是否正确
  - **新增** 测试路径 /test 无需认证，可用于验证接口连通性
  - 内部接口需提供正确的签名头，检查时间戳是否在容忍范围内
- 响应头
  - 检查 X-Trace-ID 与 X-Process-Time，用于定位问题与评估性能
- **新增** 验证错误排查
  - 查看错误响应中的详细验证信息
  - 确认请求参数是否符合 Pydantic 模型定义的约束条件

**章节来源**
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py#L104-L122)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L119-L149)

## 结论
Public API 通过清晰的路由前缀、白名单放行与统一的中间件链路，实现了高安全性、高可观测性与良好的用户体验。配合统一的异常与响应体系，第三方开发者可以快速集成并稳定地使用公开接口。**新增的验证错误测试能力进一步增强了接口的健壮性和开发体验**。建议在生产环境中严格遵循签名策略与日志追踪规范，持续优化性能指标。

## 附录

### 接口规范与使用示例
- 路由前缀：/v1/public
- 认证策略
  - Public API：白名单放行，无需 Token
  - **新增** 测试路径：白名单放行，无需 Token，便于联调
  - Internal API：需提供 X-Signature、X-Timestamp、X-Nonce
  - 普通接口：需提供有效的 Authorization Token
- **新增** 验证错误测试接口
  - POST /v1/public/test/test_validation_error：测试请求验证异常
  - 请求体：JSON格式，包含 name、age、email 字段
  - 验证规则：name长度2-20字符、age范围0-150、email格式验证
- 示例接口
  - GET /v1/public/test/test_raise_exception
  - GET /v1/public/test/test_raise_app_exception
  - GET /v1/public/test/test_contextvars_on_asyncio_task
  - GET /v1/public/test/test/sse-stream
  - GET /v1/public/chat/sse-stream/timeout

**章节来源**
- [internal/controllers/publicapi/__init__.py](file://internal/controllers/publicapi/__init__.py#L4-L11)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L57-L63)
- [internal/middlewares/auth.py](file://internal/middlewares/auth.py#L119-L149)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L15-L24)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L25-L36)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L33-L36)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L47-L75)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L84-L89)

### SDK 集成指导
- 基础调用
  - 使用 HTTPS 访问 /v1/public 下的接口
  - 对于 SSE 接口，使用浏览器或支持 EventSource 的客户端订阅
- **新增** 验证错误处理
  - 对于验证错误接口，正确设置 Content-Type: application/json
  - 按照 Pydantic 模型定义提供参数，避免验证错误
  - 解析统一响应体中的 code 与 message，结合语言参数选择展示文案
- 追踪与日志
  - 记录 X-Trace-ID 以便问题定位
  - 关注 X-Process-Time 评估接口性能

**章节来源**
- [pkg/toolkit/response.py](file://pkg/toolkit/response.py#L47-L81)
- [pkg/toolkit/response.py](file://pkg/toolkit/response.py#L195-L200)
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py#L54-L63)

### 版本管理与废弃策略
- 版本化前缀
  - 使用 /v1/public 作为版本前缀，便于未来升级与兼容
- 废弃策略
  - 新增接口时保持向后兼容，旧接口在下一个主版本中移除
  - 在文档中标注废弃时间与替代方案，提前通知开发者

**章节来源**
- [internal/controllers/publicapi/__init__.py](file://internal/controllers/publicapi/__init__.py#L4-L11)

### API 文档生成与在线测试
- 在线文档
  - Debug 模式下启用 /docs（Swagger UI）与 /redoc（ReDoc），便于联调与测试
- 文档生成
  - OpenAPI 规范由 FastAPI 自动生成，接口注释与标签有助于生成清晰的文档页面
- **新增** 验证错误测试
  - Swagger UI 中可直接测试验证错误接口
  - 支持参数验证和错误响应的可视化测试

**章节来源**
- [internal/app.py](file://internal/app.py#L19-L24)

### 请求模式定义
- **新增** 验证错误测试请求模式
  - 接口：POST /v1/public/test/test_validation_error
  - 内容类型：application/json
  - 请求体字段：
    - name: string（必填，2-20字符）
    - age: integer（必填，0-150）
    - email: string（必填，邮箱格式）
  - 成功响应：返回验证通过的参数数据
  - 错误响应：返回标准错误响应，包含详细的验证错误信息

**章节来源**
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L17-L22)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L26-L36)
- [internal/middlewares/recorder.py](file://internal/middlewares/recorder.py#L100-L101)