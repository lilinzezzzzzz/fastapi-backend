# API 接口参考

<cite>
**本文档中引用的文件**  
- [main.py](file://main.py)
- [internal/app.py](file://internal/app.py)
- [pkg/resp_tool.py](file://pkg/resp_tool.py)
- [internal/middleware/auth.py](file://internal/middleware/auth.py)
- [pkg/signature.py](file://pkg/signature.py)
- [pkg/jwt.py](file://pkg/jwt.py)
- [internal/controllers/web/user.py](file://internal/controllers/web/user.py)
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py)
- [internal/controllers/internalapi/user.py](file://internal/controllers/internalapi/user.py)
- [internal/controllers/serviceapi/user.py](file://internal/controllers/serviceapi/user.py)
</cite>

## 目录
1. [简介](#简介)
2. [访问层级与认证机制](#访问层级与认证机制)
3. [统一响应格式](#统一响应格式)
4. [Web API (/v1)](#web-api-v1)
5. [Public API (/v1/public)](#public-api-v1public)
6. [Internal API (/v1/internal)](#internal-api-v1internal)
7. [Service API (/v1/service)](#service-api-v1service)
8. [调用示例](#调用示例)

## 简介
本文档提供了 fastapi-backend 项目中所有公开 API 接口的完整参考。API 按照访问层级分为四类：Web API、Public API、Internal API 和 Service API，每类具有不同的安全要求和使用场景。所有接口均使用 `pkg.resp_tool` 中定义的统一响应格式进行标准化输出。

**Section sources**
- [main.py](file://main.py#L1-L19)
- [internal/app.py](file://internal/app.py#L1-L105)

## 访问层级与认证机制
API 接口根据其访问权限和安全要求分为四个层级，每个层级采用不同的认证机制：

- **Web API**：面向前端应用，需使用 JWT Token 认证。
- **Public API**：公开接口，无需任何认证。
- **Internal API**：内部服务间调用，使用签名认证（X-Signature、X-Timestamp、X-Nonce）。
- **Service API**：服务间调用，需使用 JWT Token 认证。

认证逻辑由 `internal.middleware.auth.ASGIAuthMiddleware` 统一处理，根据请求路径前缀进行分流验证。

```mermaid
flowchart TD
Start([请求进入]) --> PathCheck["判断路径前缀"]
PathCheck --> |/v1/public 或 /test| PublicAPI["Public API: 无需认证"]
PathCheck --> |/v1/internal| InternalAPI["Internal API: 验证 X-Signature, X-Timestamp, X-Nonce"]
PathCheck --> |其他路径| TokenCheck["检查 Authorization Header"]
TokenCheck --> |Bearer Token| JWTVerify["验证 JWT Token"]
TokenCheck --> |无 Token| Unauthorized["返回 401"]
JWTVerify --> |验证失败| Unauthorized
JWTVerify --> |验证成功| SetContext["设置用户上下文"]
PublicAPI --> Process
InternalAPI --> Process
SetContext --> Process
Process([处理请求]) --> Response["返回响应"]
```

**Diagram sources**
- [internal/middleware/auth.py](file://internal/middleware/auth.py#L1-L93)
- [pkg/signature.py](file://pkg/signature.py#L1-L102)
- [pkg/jwt.py](file://pkg/jwt.py#L1-L39)

**Section sources**
- [internal/middleware/auth.py](file://internal/middleware/auth.py#L1-L93)
- [pkg/signature.py](file://pkg/signature.py#L1-L102)
- [pkg/jwt.py](file://pkg/jwt.py#L1-L39)

## 统一响应格式
所有 API 接口均使用 `pkg.resp_tool.ResponseFactory` 提供的统一响应格式。标准响应结构如下：

```json
{
  "code": 20000,
  "message": "",
  "data": {}
}
```

### 常用响应方法
| 响应方法 | HTTP 状态码 | 业务码 | 说明 |
|--------|-----------|--------|------|
| `resp_200` | 200 | 20000 | 成功响应 |
| `resp_400` | 400 | 40000 | 请求错误 |
| `resp_401` | 401 | 40001 | 未授权 |
| `resp_403` | 403 | 40003 | 禁止访问 |
| `resp_404` | 404 | 40004 | 资源未找到 |
| `resp_422` | 422 | 40005 | 参数验证失败 |
| `resp_500` | 500 | 50000 | 服务器内部错误 |

响应体中的 `code` 字段为业务码，`message` 为描述信息，`data` 为实际数据内容。该机制确保了前后端交互的一致性和可预测性。

**Section sources**
- [pkg/resp_tool.py](file://pkg/resp_tool.py#L1-L209)

## Web API (/v1)
Web API 位于 `/v1` 前缀下，主要供前端 Web 应用调用，需要 JWT Token 认证。

### /test/hello_world
返回一个简单的成功响应。

- **HTTP 方法**: GET
- **URL 路径**: `/v1/test/hello_world`
- **请求头**:
  - `Authorization`: Bearer {JWT Token}
- **请求参数**: 无
- **响应状态码**:
  - `200`: 成功
  - `401`: 未授权（Token 无效或缺失）
- **响应体结构**:
```json
{
  "code": 20000,
  "message": "",
  "data": null
}
```

**Section sources**
- [internal/controllers/web/user.py](file://internal/controllers/web/user.py#L1-L13)

## Public API (/v1/public)
Public API 位于 `/v1/public` 前缀下，为公开接口，无需任何认证即可访问。

### /test/test_raise_exception
测试抛出普通异常。

- **HTTP 方法**: GET
- **URL 路径**: `/v1/public/test/test_raise_exception`
- **请求头**: 无
- **请求参数**: 无
- **响应状态码**:
  - `500`: 服务器内部错误
- **响应体结构**:
```json
{
  "code": 50000,
  "message": "Internal Server Error, test_raise_exception",
  "data": null
}
```

### /test/test_custom_response_class_basic_types
测试自定义响应类对基本类型的支持。

- **HTTP 方法**: GET
- **URL 路径**: `/v1/public/test/test_custom_response_class_basic_types`
- **请求头**: 无
- **请求参数**: 无
- **响应状态码**:
  - `200`: 成功
- **响应体结构**:
```json
{
  "code": 20000,
  "message": "",
  "data": {
    "large_int": "9007199254740993",
    "normal_int": 42,
    "float_num": 3.1415926535,
    "boolean": true,
    "none_value": null
  }
}
```

### /test/test_dao
测试数据访问对象（DAO）的各种数据库操作。

- **HTTP 方法**: GET
- **URL 路径**: `/v1/public/test/test_dao`
- **请求头**: 无
- **请求参数**: 无
- **响应状态码**:
  - `200`: 成功
  - `500`: 操作失败
- **响应体结构**:
```json
{
  "code": 20000,
  "message": "",
  "data": null
}
```

### /test/sse-stream
测试服务器发送事件（SSE）流式响应。

- **HTTP 方法**: GET
- **URL 路径**: `/v1/public/test/sse-stream`
- **请求头**: 无
- **请求参数**: 无
- **响应状态码**:
  - `200`: 成功（流式传输）
- **响应体结构**: SSE 格式的文本流
```
data: hello，正在查询资料

data: 正在组织回答

data: 开始回答
...
```

**Section sources**
- [internal/controllers/publicapi/test.py](file://internal/controllers/publicapi/test.py#L1-L301)

## Internal API (/v1/internal)
Internal API 位于 `/v1/internal` 前缀下，用于内部服务间的安全调用，必须使用签名认证。

### /user/hello-world
返回一个简单的成功响应，用于测试内部接口连通性。

- **HTTP 方法**: GET
- **URL 路径**: `/v1/internal/user/hello-world`
- **请求头**:
  - `X-Signature`: 签名字符串
  - `X-Timestamp`: UTC 秒级时间戳
  - `X-Nonce`: 随机字符串
- **请求参数**: 无
- **响应状态码**:
  - `200`: 成功
  - `401`: 未授权（签名验证失败）
- **响应体结构**:
```json
{
  "code": 20000,
  "message": "",
  "data": null
}
```

**Section sources**
- [internal/controllers/internalapi/user.py](file://internal/controllers/internalapi/user.py#L1-L11)

## Service API (/v1/service)
Service API 位于 `/v1/service` 前缀下，用于服务间调用，需要 JWT Token 认证。

### /user
返回一个简单的成功响应，用于测试服务接口。

- **HTTP 方法**: GET
- **URL 路径**: `/v1/service/user`
- **请求头**:
  - `Authorization`: Bearer {JWT Token}
- **请求参数**: 无
- **响应状态码**:
  - `200`: 成功
  - `401`: 未授权（Token 无效或缺失）
- **响应体结构**:
```json
{
  "code": 20000,
  "message": "",
  "data": null
}
```

**Section sources**
- [internal/controllers/serviceapi/user.py](file://internal/controllers/serviceapi/user.py#L1-L11)

## 调用示例
以下为各类型 API 的调用示例。

### Web API 调用示例 (curl)
```bash
curl -X GET "http://localhost:8000/v1/test/hello_world" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Web API 调用示例 (Python requests)
```python
import requests

url = "http://localhost:8000/v1/test/hello_world"
headers = {
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}

response = requests.get(url, headers=headers)
print(response.json())
```

### Internal API 调用示例 (curl)
```bash
curl -X GET "http://localhost:8000/v1/internal/user/hello-world" \
  -H "X-Signature: a1b2c3d4e5f6g7h8i9j0" \
  -H "X-Timestamp: 1700000000" \
  -H "X-Nonce: abcdef123456"
```

### Internal API 调用示例 (Python requests)
```python
import requests
import time
import hashlib
import hmac

def generate_signature(secret_key, timestamp, nonce):
    data = f"timestamp={timestamp}&nonce={nonce}"
    signature = hmac.new(
        secret_key.encode(),
        data.encode(),
        hashlib.sha256
    ).hexdigest()
    return signature

url = "http://localhost:8000/v1/internal/user/hello-world"
timestamp = str(int(time.time()))
nonce = "abcdef123456"
secret_key = "your-secret-key"
signature = generate_signature(secret_key, timestamp, nonce)

headers = {
    "X-Signature": signature,
    "X-Timestamp": timestamp,
    "X-Nonce": nonce
}

response = requests.get(url, headers=headers)
print(response.json())
```