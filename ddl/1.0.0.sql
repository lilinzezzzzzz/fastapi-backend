CREATE TABLE `documents` (
  `id` bigint NOT NULL COMMENT '文档唯一标识 (UUID)',
  `organization_id` bigint NOT NULL COMMENT '租户隔离ID',
  `filename` VARCHAR(255) NOT NULL COMMENT '原始文件名',
  `storage_path` VARCHAR(512) NOT NULL COMMENT 'S3/OSS 中的对象Key',
  `storage_type` VARCHAR(16) NOT NULL COMMENT '存储类型',
  `file_size` BIGINT UNSIGNED DEFAULT 0 COMMENT '文件大小（字节）',
  `mime_type` VARCHAR(128) DEFAULT NULL COMMENT '文件类型 (如 application/pdf)',
  `status` VARCHAR(32) COMMENT '状态:uploading,unprocessed,parsing,completed,cancelled,failed',
  `language` VARCHAR(8) DEFAULT NULL COMMENT '文档原始语言',
  `error_msg` text DEFAULT '' COMMENT '解析失败的错误信息',
  `is_deleted` BOOL NOT NULL DEFAULT false,
  `creator_id` BIGINT NOT NULL,
  `created_at` DATETIME NOT NULL,
  `updater_id` BIGINT DEFAULT NULL,
  `updated_at` DATETIME DEFAULT NULL,
  -- 约束与索引
  PRIMARY KEY (`id`),
  INDEX `idx_organization_id` (`organization_id`) USING BTREE COMMENT '租户查询索引',
  INDEX `idx_created_at` (`created_at`) COMMENT '按时间排序索引'
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci COMMENT = '知识库文档主表';
