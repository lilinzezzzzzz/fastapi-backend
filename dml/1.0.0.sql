CREATE TABLE `user`
(
    `id`         bigint unsigned NOT NULL AUTO_INCREMENT,
    `username`   varchar(64) COLLATE utf8mb4_general_ci NOT NULL,
    `phone`      varchar(11) COLLATE utf8mb4_general_ci NOT NULL,
    `account`    varchar(32) COLLATE utf8mb4_general_ci NOT NULL,
    `created_at` datetime                               NOT NULL ON UPDATE CURRENT_TIMESTAMP,
    `updated_at` datetime                               NOT NULL ON UPDATE CURRENT_TIMESTAMP,
    `deleted_at` datetime DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `username_unique` (`username`) USING BTREE,
    UNIQUE KEY `phone_unique` (`phone`) USING BTREE,
    KEY          `account` (`account`) USING BTREE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;