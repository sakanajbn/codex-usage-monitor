# 设计说明

## 目标

只读读取本地 Codex 会话日志，展示指定时间窗口内的 token 消耗与缓存命中率。程序不访问任何网络接口，不读取或显示会话正文。

## 数据口径

- 数据目录：优先读取 `CODEX_HOME`，未设置时读取 `%USERPROFILE%\.codex`。
- 数据文件：递归扫描 `sessions\**\*.jsonl`。
- 有效事件：顶层 `type=event_msg`、`payload.type=token_count`，且包含 `payload.info.last_token_usage`。
- 时间窗口：`1h`、`8h`、`16h`、`24h`、`3天`、`7天`、`30天`、`60天`、`90天`，默认 `24h`。
- 消耗 token：未缓存输入 + 缓存输入 + 输出。当前 Codex 格式中 `last_token_usage.input_tokens` 已包含 `cached_input_tokens`，因此数值上等于 `input_tokens + output_tokens`，缓存不重复相加；使用 `last_token_usage`，不累加累计字段 `total_token_usage`。
- 输入展示：未缓存输入为 `max(input_tokens - cached_input_tokens, 0)`，缓存输入单独展示。
- 旧版格式兼容：若 `total_tokens - output_tokens` 大于上报的 `input_tokens`，按该值归一化总输入，以覆盖“输入与缓存分列”的旧日志。
- 缓存命中率：`cached_input_tokens / input_tokens * 100`，输入为 0 时显示 `--`。
- 压缩估算事件：输入、缓存、输出均为 0 但 `total_tokens` 非 0 的事件视为估算值并忽略。

## 架构

PySide6 + PyInstaller 的 Windows x64 单文件应用，分三层：

1. `CodexUsageReader`（`reader.py`）负责本地 JSONL 的只读扫描、容错解析和统计聚合。
2. `UsageSnapshot`（`models.py`）作为读取器与 UI 之间的不可变数据契约。
3. `MainWindow`（`main_window.py`）负责指标卡片、状态提示、手动刷新和 15 秒自动刷新。

读取器按文件维护增量缓存：文件大小与修改时间未变时复用已解析事件，追加写入时只解析新增字节。所有文件以共享读方式打开，Codex 正在写入时也可安全读取；单个锁定文件、半行 JSON 或损坏行只计入诊断，不阻断其他文件的统计。

## 界面

- 窗口标题与品牌名：`Codex 监控面板`。
- 主指标：所选窗口的消耗 token 与缓存命中率。
- 辅助指标：输入 token（不含缓存）、缓存 token、输出 token、有效事件数。
- 状态区：数据源路径、最后刷新时间、最近事件时间、错误或跳过文件数。
- 控件：`1h/8h/16h/24h` 直显按钮 + 长窗口下拉框，以及手动刷新按钮。

## 错误处理

| 情况 | 行为 |
|---|---|
| Codex 目录不存在 | 状态区显示“未找到本地 Codex 数据目录” |
| 没有有效事件 | 指标显示 0 / `--`，说明当前窗口无可用记录 |
| 部分文件读取失败 | 保留成功统计，并显示跳过文件数 |
| 存在损坏 JSON 行 | 保留其余统计，并显示跳过行数 |
| 刷新失败 | 保留最近一次成功快照，状态区显示本次错误 |
