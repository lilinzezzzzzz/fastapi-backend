from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database.base import ModelMixin


class User(ModelMixin):
    """用户表

    ```sql
    CREATE TABLE `user` (
        `id` BIGINT NOT NULL COMMENT '主键 ID',
        `username` VARCHAR(64) NOT NULL COMMENT '用户名',
        `account` VARCHAR(64) NOT NULL COMMENT '账号',
        `phone` VARCHAR(11) NOT NULL COMMENT '手机号',
        `password_hash` VARCHAR(255) DEFAULT NULL COMMENT '密码哈希',
        `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
        `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
        `is_deleted` TINYINT NOT NULL DEFAULT 0 COMMENT '是否删除',
        `deleted_at` DATETIME DEFAULT NULL COMMENT '删除时间',
        PRIMARY KEY (`id`),
        UNIQUE KEY `uq_account` (`account`),
        UNIQUE KEY `uq_phone` (`phone`),
        INDEX `idx_username` (`username`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';
    ```
    """

    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(64), comment="用户名")
    account: Mapped[str] = mapped_column(String(64), comment="账号")
    phone: Mapped[str] = mapped_column(String(11), comment="手机号")
    password_hash: Mapped[str | None] = mapped_column(String(255), comment="密码哈希")
