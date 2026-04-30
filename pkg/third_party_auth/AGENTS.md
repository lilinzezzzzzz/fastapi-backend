# AGENTS.md

适用于 `pkg/third_party_auth/`。父级约束见 `pkg/AGENTS.md`。

## 模块职责

第三方登录的策略 + 工厂抽象：

- `base.py`：`BaseThirdPartyAuthStrategy`、`ThirdPartyUserInfo` 数据类。
- `config.py`：平台通用配置基类（如 `WeChatConfig`）。
- `factory.py`：`ThirdPartyPlatform` 枚举、`ThirdPartyAuthFactory`。
- `strategies/<platform>.py`：具体平台实现（目前 `wechat`）。

## 编码约定

- 新增平台步骤：
  1. 在 `ThirdPartyPlatform` 增加枚举值；
  2. 在 `config.py` 定义 `<Platform>Config` 数据类（仅结构，无 I/O）；
  3. 在 `strategies/<platform>.py` 继承 `BaseThirdPartyAuthStrategy` 实现；
  4. 在 `ThirdPartyAuthFactory` 注册；
  5. 在 `__init__.py` 导出必要类型。
- 配置通过构造函数注入（遵循策略接口），禁止从 `internal.config.settings` 直接读取，保持包可独立复用。
- 策略内部的 HTTP 客户端必须可关闭（提供 `close()` 或 async context manager），调用方按 `try/finally` 释放资源。
- 返回结构统一走 `ThirdPartyUserInfo`；不同平台字段差异在策略内部归一化完成，不把原始响应外泄到上层 Service。

## 兼容性要求

- `BaseThirdPartyAuthStrategy` 的抽象方法签名和 `ThirdPartyUserInfo` 字段是跨业务契约，修改必须全仓检索调用方并补测试。
- `ThirdPartyPlatform` 枚举值是持久化 artifact（用于 `third_party_account` 表），改名 / 删除需要数据迁移。

## 验证重点

- 使用 mock HTTP 客户端覆盖 token 换取、用户信息获取、错误响应三条主路径。
- 不允许在测试中向真实第三方服务发起请求。
