# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.4.2] - 2026-08-14

### Added

- **嫌疑提示字体**：疑似小号（高嫌疑 / 一键拉黑标记）、黑名单用户、非白名单用户（白名单模式下）在主界面显示的名称以彩色标出，默认红色；可在「设置 → 嫌疑提示字体」自定义颜色（`suspect_name_color`）

## [1.4.1] - 2026-08-14

### Changed

- **去除「内存扫描版」名称**：统一为 AntiSmurf 单一版本；产物名改为 `AntiSmurf.exe` / `AntiSmurf-Setup-x.y.z.exe` / `AntiSmurf-x.y.z-portable.zip`（窗口标题、安装包名称、README/docs 同步更新）
- **安装包说明精简**：去除开源许可（LICENSE）相关内容，仅保留源代码 GitHub 地址
- **功能说明优化**：README 功能列表补全（内存模式 6 大厅识别 / 句柄位置自适应 / 窥屏者检测 / 白名单模式 / 批量白名单 / AI 助手与 IDE 编辑规则 / 分数着色 / 一键拉黑等）

## [1.4.0] - 2026-08-14

### Added

- **句柄位置自动/手动更新**：游戏版本更新导致固定跳转（SC2_x64.exe+0x3E2F340）失效时，自动在主机句柄附近嗅探多格式存储（ASCII / profile_triplet / 指针间接），结合附近信息（profile_id 字段 / struct 头 0x5332 / 显示名）解读确认主机句柄
- **位置确认状态**：主界面状态栏显示「句柄位置=已确认/未确认」与「玩家句柄=已抓到」；房间无玩家时通过主机句柄附近嗅探确认抓取能力
- **手动刷新策略**：已确认句柄位置时刷新仅重新读取（不嗅探）；1.5 秒内多次刷新自动强制重新确认位置
- **嗅探结果持久化**：确认的新主机句柄模块偏移自动写入校准档（data/probe_calibration.json），下次启动免嗅探直接使用
- 配置项：`memory.host_anchor_sniff_enabled`、`memory.handle_reconfirm_threshold_sec`（默认 1.5）

## [1.3.1] - 2026-08-09

### Added

- **批量添加白名单**：主界面「批量白名单」对话框支持一次粘贴多个句柄
  - 自动识别分隔符（空格 / 逗号 / 中文逗号 / 分号 / 顿号 / 换行）
  - 纯数字自动补全句柄开头 `5-S2-1-`（不定长数字）
  - 合法性校验：非法内容列出并跳过，不添加

## [1.3.0] - 2026-08-04

### Added

- **AI 规则助手**：规则编辑器「AI 助手」填写 API Key（OpenAI 兼容：DeepSeek / Kimi / OpenAI / OpenRouter）用自然语言生成评分规则，自动校验后追加
- **本地 IDE 编辑规则**：规则编辑器「IDE 编辑」导出规则文件并用 VSCode（或系统默认编辑器）打开，修改后「从文件重载」应用
- **白名单模式**：主界面一键切换，自动踢出白名单（数据库白名单 + handle_trust_rules）以外的所有玩家，默认保持黑名单模式
- README 新增「用 AI 助手编写规则」与「白名单模式」文档（变量表 / 运算符 / 提示词示例 / API Key 配置表）

## [1.2.1] - 2026-08-04

### Fixed

- 同局判定改为分钟精度：对局时间精确到分钟即视为同一场（不再按秒窗口），更贴合实际对局时间
- 凯瑞甘阵营判定按角色名单（Kerrigan / Zagara / Dehaka / Thakras / Niadra / Brakk / Glevig / Phaegore / Izsha / Malus / Kraith / Sir Roachington），不依赖 API 的 side 字段
- 功能语义明确为「识别窥屏者」：通知与规则原因文案更新（窥屏嫌疑：与主机同一对局时凯瑞甘 MMR 异常升高）

## [1.2.0] - 2026-08-04

### Added

- 同局凯瑞甘 MMR 异常检测：玩家与主机 30 秒内同一对局、且凯瑞甘阵营评估 MMR 异常升高（反推核心 − 凯瑞甘核心 ≥ 400）时，每次 +20 嫌疑分
- 命中时同会话弹出一次通知，提示嫌疑对象、累计次数与嫌疑原因
- 检测阈值/窗口/每次加分可在 `config/user.toml` 调整（same_match_* 配置项）

## [1.1.2] - 2026-08-01

### Added

- 分数按值着色（可配置，默认 +分红色 / −分绿色 / 0 分白色），应用于主界面与识别历史界面
- 设置对话框新增分数颜色配置（正分/负分/零分）

### Changed

- 一键拉黑优化：主界面「拉黑+200」与历史界面按钮改为一键拉黑（加入黑名单并写入 handle_mark_rules，+200 嫌疑分），替代原「标记+100」

## [1.1.1] - 2026-08-01

### Added

- 主界面「刷新」按钮：手动立即扫描房间玩家信息并重新评估确认

### Fixed

- `.gitignore` 误伤 `src/antismurf/data` 源码包导致 CI 失败（改为锚定根目录）
- `build.spec` 移除已清理的 `target/` 目录引用

## [1.1.0] - 2026-07-06

### Added

- **识别历史**：持久化玩家 MMR/PL 快照，支持记录时与查看时自动对比变化
- **信任白名单 -20**：句柄匹配 `handle_trust_rules` 减 20 嫌疑分（对照手动标记 +100）
- **主界面说明**：各列参数含义与初次 UI 校准步骤
- **录像与积分**：194823 社区积分查询与兑奖指令（合并原数据源入口）
- **快捷标记 +100**：主界面与历史页一键写入 `handle_mark_rules`
- Memory Mode 6 大厅 faction MMR/PL 列（核心·前三·均值）
- KS2 Wiki / 194823 社区 MMR + playlike 查询
- balanced 预设规则：Top3 抬升、低场次、近期 PL 增长等

### Changed

- 嫌疑阈值默认 20 / 60 / 100（中 / 高 / 踢人）
- 打包构建启用自动踢人（`AUTO_KICK_ENABLED = true`）

### Fixed

- Inno Setup 单候选路径被误解析为首字符导致安装包路径错误

## [1.0.0] - 2026-07-06

### Added

- Script-based kick (right-click slot + menu offset) without OCR/UIA dependency
- Drag-to-position calibration overlay for slot anchors and kick menu offset
- Room presence debouncing to reduce in/out flicker from transient memory reads

### Changed

- First stable release: auto-kick enabled in packaged builds (`AUTO_KICK_ENABLED = true`)
- Orchestrator treats debounced in-room state as authoritative (no longer requires non-empty handles)

### Fixed

- Calibration overlay crash (`bad screen distance "0 8"`) that closed the calibration window
- Room state instability from cache clearing on single read miss and aggressive periodic rescans

## [1.1.0-gray] - 2026-07-06

### Added

- Memory Mode 6 lobby roster scan (bidirectional anchor scan, team tag parsing)
- KS2 Wiki / 194823 community MMR + playlike lookup (`provider = ks2wiki`)
- Main UI faction MMR / playlike columns (core, top-3, mean)
- Expression rules: `MMRplaylike.max − MMR.min > 800`, `handle.profile_id > 12500000`

### Changed

- Gray release: **OCR / menu auto-kick disabled** (`AUTO_KICK_ENABLED = false`); scoring and manual kick remain
- Default `auto_kick_enabled = false`, `dry_run = true`

### Fixed

- Host-not-slot-0 roster discovery via forward/backward memory scan

## [1.1.0] - (pre-gray)

### Added

- Player roster sync (CSV/XLSX) and shareable TOML rule packs
- Local replay scan with handle/display-name bindings (`data/replay_bindings.db`)
- Replay filename priority for `凯瑞甘生存2 最新版`
- GitHub CI, contribution docs, and release maintenance guides

### Fixed

- SC2 replay parsing with sc2reader 1.8 (`register_all` removal)

## [1.0.0] - 2026-06-24

### Added

- PaddleOCR lobby vision for KS2 map and player ID detection
- KS2 Wiki / community scoring and configurable expression rules
- Windows portable exe and Inno Setup installer build scripts
- Local replay indexing, auto-upload hook, GUI calibration

[Unreleased]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/compare/v1.4.2...HEAD
[1.4.2]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.4.2
[1.4.1]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.4.1
[1.4.0]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.4.0
[1.3.1]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.3.1
[1.3.0]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.3.0
[1.2.1]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.2.1
[1.2.0]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.2.0
[1.1.2]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.1.2
[1.1.1]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.1.1
[1.1.0]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.1.0
[1.0.0]: https://github.com/STCrazyCat/KerriganSurvival2Antismurf/releases/tag/v1.0.0
