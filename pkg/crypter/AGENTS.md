# AGENTS.md

适用于 `pkg/crypter/`。父级约束见 `pkg/AGENTS.md`。

## 模块职责

通用加密能力抽象。对外暴露 `EncryptionAlgorithm` 枚举、`BaseCipher` 抽象基类、`get_crypto_class()` 工厂，以及具体实现（如 `AESCipher`）。

- 被 `internal/config.py` 的 `ENC(...)` 解密链路依赖，任何行为变更都要考虑配置兼容性。

## 编码约定

- 新增算法按现有模式：实现 `BaseCipher`，通过 `EncryptionAlgorithm` 枚举和工厂函数注册；不要绕过工厂暴露新入口。
- 加密/解密接口保持同步，I/O 由调用方决定。
- 公开方法不得在日志中打印明文、密钥或中间缓冲；错误消息也不允许泄漏长度、盐、IV 等可被侧信道利用的细节。
- 异常使用模块内明确类型，不直接抛 `ValueError` / `Exception`；便于上层转为 `AppException`。

## 兼容性要求

- 密文格式（头部、编码、分隔符）是跨部署 artifact。变更前必须：
  - 确认所有使用方可重新加密或提供兼容解密。
  - 保留旧密文的解密路径或提供迁移脚本。
- 密钥长度、派生方式、模式（CBC/GCM 等）属于稳定契约，改动按 `BREAKING CHANGE` 对待。

## 验证重点

- 覆盖加密 → 解密、错误密钥、错误密文、长度边界四类路径。
- 修改算法参数后必须回归 `ENC(...)` 配置解密场景。
