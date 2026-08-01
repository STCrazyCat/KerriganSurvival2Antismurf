# 评分规则校准指南

完整用户手册见 **[规则设置手册.md](./规则设置手册.md)**（含 UI 校准、变量表、踢人配置与常见问题）。

## 默认规则（balanced 预设）

| 表达式 | 得分 |
|--------|------|
| `MMRplaylike.max − MMR.min > 800` | 80 |
| `句柄末段 (profile ID) > 12500000` | 20 |

合计 **100 分**时自动踢出（`kick_threshold = 100`，需 `auto_kick_enabled = true` 且非 `dry_run`）。

其余规则由玩家在「评分规则」编辑器中自行添加。

## 规则编辑器

- **值 A**、可选 **算术运算**（±×÷）、**值 B**，再与**比较值**比较
- 条件为真（得 1）时加上「权重(真)」分
- 变量从分类菜单插入；角色相关可手动输入 `role.mmr.Energizer`、`role.playlike.Energizer`

### 内置变量

| 变量 | 说明 |
|------|------|
| `handle.profile_id` | 句柄末段数字（5-S2-1-**12345678** 只用 12345678） |
| `player.has_team` | 是否有战队名（0/1） |
| `mmr.survivor` / `mmr.kerrigan` | 各阵营核心 MMR |
| `mmr_playlike.survivor` / `mmr_playlike.kerrigan` | 反推核心 MMRplaylike |
| `role.mmr.{角色名}` | 该角色官方 MMR（含 class 偏移） |
| `role.playlike.{角色名}` | 该角色近期 playlike 均值 |

| `data.community_match_count` | 社区各角色 `plays` 之和 |

## 调参

- 在 GUI 加载 `balanced` 可恢复默认两条规则
- 导出/导入规则包便于分享自定义配置
