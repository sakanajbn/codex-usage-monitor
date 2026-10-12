# Codex 监控面板

只读读取本地 Codex 会话日志的 Windows 桌面监控面板，展示 token 消耗、缓存命中率和数据源状态。

程序只扫描本地 JSONL 文件，**不访问任何网络接口**，不读取或显示提示词、回答、工具输出等会话正文。

## 功能

- 九档统计窗口：`1h`、`8h`、`16h`、`24h`，以及下拉框中的 `3天`、`7天`、`30天`、`60天`、`90天`。
- 主指标：所选窗口的消耗 token、缓存命中率。
- 辅助指标：输入 token（不含缓存）、缓存 token、输出 token、有效事件数。
- 每 15 秒自动刷新，也可手动刷新。
- 数据源状态、最近事件时间和异常诊断提示。

## 安装与运行

需要 Python 3.10+。

```powershell
pip install PySide6
$env:PYTHONPATH = "src"
python -m codex_monitor.main
```

或以可编辑方式安装后直接运行：

```powershell
pip install -e .
codex-monitor
```

## 数据来源

程序按以下顺序定位数据目录：

1. 环境变量 `CODEX_HOME` 指向的目录；
2. 未设置时使用 `%USERPROFILE%\.codex`。

然后递归扫描其下的 `sessions\**\*.jsonl`，只提取 `token_count` 事件中的 `last_token_usage`。统计口径详见 [设计说明](docs/design.md)。

## 构建 Windows 可执行文件

```powershell
pip install pyinstaller
pyinstaller --noconfirm --clean --distpath ./outputs ./packaging/Codex监控面板_win_x64.spec
```

产物位于 `outputs/Codex监控面板_win_x64.exe`（单文件，目标机器无需安装 Python）。

## 测试

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

共 16 项测试，覆盖时间窗口过滤、累计字段不重复统计、旧格式归一化、损坏行容错、增量读取、UI 契约和打包配置。

## 项目结构

```text
.
├─ src/codex_monitor/     # 应用源码
├─ tests/                 # unittest 测试
├─ packaging/             # PyInstaller 打包配置
├─ docs/design.md         # 统计口径与架构设计
├─ pyproject.toml
└─ LICENSE
```

## 隐私边界

- 只读打开本地 Codex 文件，不修改、不删除。
- 不读取会话正文、提示词、工具输出或凭据字段。
- 不发起任何网络请求。

## 许可证

[MIT](LICENSE)
