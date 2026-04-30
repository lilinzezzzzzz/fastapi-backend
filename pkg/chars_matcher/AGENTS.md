# AGENTS.md

适用于 `pkg/chars_matcher/`。父级约束见 `pkg/AGENTS.md`。

## 模块职责

中文候选字匹配包，对外暴露统一入口 `CharsMatcher` / `default_chars_matcher` / `preload`，内部拆成两条独立子管线：

- `PinyinCharsMatcher`：基于拼音的候选字匹配与姓氏匹配。
- `ShapeCharsMatcher`：基于部件 / 相邻字的字形近似匹配。

## 编码约定

- 新增匹配维度（例如语义、五笔）时，遵循现有拆分：
  - 独立子匹配器类 `XxxCharsMatcher`，放在 `pkg/chars_matcher/xxx_chars_matcher.py`。
  - 数据文件放在 `chars/xxx/`，命名空间不与其他维度冲突。
  - `matcher.py` 仅做编排，不承担具体匹配算法。
- 共享类型统一在 `types.py`（`PinyinCharMapping`、`ShapeFeatureMapping`、`CharMatchType`、`MatchType`）。
- 数据加载使用异步预加载 + 懒初始化；模块顶层不做阻塞 I/O。
- 数据校验、重建走 `validation.py` 和 `scripts/`，应用代码路径不引入 `scripts/` 依赖。

## 数据文件约定

- `chars/pinyin/pinyin_chars.json`、`chars/pinyin/surname_pinyin_chars.json`、`chars/shape/name_shape_chars.json` 是对外稳定 artifact，修改格式前全仓检索使用方。
- 更新数据使用 `scripts/rebuild_chars_matcher_pinyin_mappings.py` 生成，不要手改 JSON 大批量条目；脚本必须幂等。

## 验证重点

- 调整数据结构、公开类或 `preload` 行为时，先跑 `pkg/chars_matcher` 相关调用方最小测试。
- 首次加载竞态、异步并发预加载路径需要覆盖。
