# AGENTS.md

适用于 `pkg/oss/`。父级约束见 `pkg/AGENTS.md`。

## 模块职责

对象存储抽象层：以 `BaseStorage` 定义统一契约，具体后端（Aliyun OSS、S3 等）通过 `@register_storage` 注册到 `_STORAGE_REGISTRY`。

- `base.py`：`StorageType` 枚举、`BaseStorage` 抽象基类、`register_storage` 装饰器。
- `aliyun.py` / `s3.py`：具体后端实现。

## 编码约定

- 新增后端步骤：
  1. 在 `StorageType` 增加枚举值；
  2. 新文件 `pkg/oss/<name>.py` 实现 `BaseStorage` 全部抽象方法；
  3. 用 `@register_storage(StorageType.XXX)` 装饰类；
  4. 在 `__init__.py` 的 re-export 中补上。
- 所有公开方法必须是 `async`；禁止在后端内使用同步阻塞 SDK 调用（必要时走 `anyio.to_thread`）。
- 路径参数 `path` 以 POSIX 相对路径形式传入，不要在底层实现里拼 bucket 名或绝对 URL；前缀由构造函数持有。
- 凭证（AK/SK、endpoint、bucket）通过构造函数注入，不从环境变量或全局 settings 直接读取。
- 错误抛出自有异常类型，便于上层转换成 `AppException`；不吞掉原始 SDK 错误上下文。

## 兼容性要求

- `BaseStorage` 抽象方法签名（`upload` / `generate_presigned_url` / `delete` / `exists` 等）是稳定契约，修改签名必须同步全部后端和调用方。
- 返回值语义（例如 upload 返回访问 URL 还是 object key）需要在 `BaseStorage` docstring 显式约束，所有后端严格遵守。

## 验证重点

- 新增或修改后端时，使用 mock SDK 覆盖 upload / delete / exists / presign 四个主路径。
- 不要把真实 bucket 或凭证写入测试；使用环境 stub 或 moto 等方案。
