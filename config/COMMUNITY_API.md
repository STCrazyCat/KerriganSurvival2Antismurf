数据源（可选，默认 `provider = "disabled"`）：

| 站点 | 用途 |
|------|------|
| [wiki.ks2.top](https://wiki.ks2.top/lookup) | KS2 Wiki 玩家查询 |
| [194823.xyz](https://194823.xyz/) | 工具站（同一 MMR 后端，参数名不同） |

两个站点的前端均为 SPA，**不解析 HTML**；直接请求 JSON API。

## 句柄格式

`{region}-S2-{realm}-{profile_id}`，例如 `5-S2-1-6738824`。

## wiki.ks2.top

### 核心 MMR + 各角色 class_mmr

```
GET https://wiki.ks2.top/api/mmr?handle=5-S2-1-6738824
```

- `200`：JSON，含 `cores.survivor` / `cores.kerrigan`、各 `roles_*` 列表
- `204`：无记录

字段说明：

| 字段 | 含义 |
|------|------|
| `cores.survivor` / `cores.kerrigan` | 各阵营**核心 MMR**（账号在该阵营的基础分） |
| `roles_*.core_mmr` | 与对应 `cores.*` 相同 |
| `roles_*.class_mmr` | 该角色相对核心的偏移 |
| `roles_*.mmr` | `core_mmr + class_mmr`（该角色官方 MMR） |

### 近期对局 playlike（MMR_playlike 来源）

```
GET https://wiki.ks2.top/api/played_like?handle=5-S2-1-6738824
```

```json
{
  "identity": "CrazyCat#592531",
  "through": "2026-07-02 12:47:48",
  "games": [
    {
      "date": "2026-07-01 02:39:04",
      "role": "Energizer",
      "team": 0,
      "estimated": 1699,
      "played_like": 2110.015625
    }
  ]
}
```

| 字段 | 含义 |
|------|------|
| `played_like` | 该局表现反推的 MMR |
| `estimated` | 该角色当时估算 MMR |
| `team` | `0` = 生存者，`1` = 凯瑞甘 |

**反推核心 playlike**（单局）：`inferred_core = played_like - class_mmr`（用 `/api/mmr` 中该角色的 `class_mmr`）。

## 194823.xyz

玩家页 `GET /player/{handle}` 仅为 SPA 壳；数据来自：

```
GET https://194823.xyz/api/player?player_handle=5-S2-1-6738824
```

响应与 wiki 的 `/api/mmr` **相同**（同一 `generated_at` 与 payload），但查询参数名为 **`player_handle`** 而非 `handle`。

194823 **未暴露** `/api/played_like`；AntiSmurf 在使用 `provider = "194823"` 时会从 wiki 拉取 playlike。

### 积分与兑奖指令

```
GET https://194823.xyz/api/credits?player_handle=5-S2-1-6738824
```

响应示例：

```json
{
  "replays": 524,
  "code": "<兑奖指令，粘贴到 SC2 聊天>",
  "penalty": 0,
  "updated": 1783333801.845319
}
```

| 字段 | 含义 |
|------|------|
| `replays` | 上传积分（录像上传累计） |
| `code` | 兑奖指令（AntiSmurf「录像与积分」页查询后自动复制） |
| `penalty` | 罚分 |

参数名必须为 **`player_handle`**（不是 `handle`）。

## AntiSmurf 配置

```toml
[community]
provider = "ks2wiki"   # 或 "194823"
base_url = "https://wiki.ks2.top"   # 194823 时改为 https://194823.xyz
```

## 评分语义（核心）

炸鱼检测关注：**核心 MMR 偏低的账号**，是否在**多局**对局中 `played_like`（反推核心）**异常高于**该阵营 `core_mmr`。

| 指标 | 含义 |
|------|------|
| `spike.count` | 单局 `inferred_core - core_mmr >= 400` 的对局数 |
| `spike.max` | 上述超出幅度的最大值 |
| `lift.core_*` | 反推核心 playlike 均值 − 阵营核心 MMR |

**不应**使用两阵营 `cores` 之差，或「核心 MMR 高、playlike 均值低」作为炸鱼主信号。

## 其他 provider

| provider | 说明 |
|----------|------|
| `disabled` | 默认，不查询 |
| `ks2wiki` | Wiki API |
| `194823` | 工具站 MMR + Wiki playlike |
| `stub` | 本地 `config/community_stub.json` |
| `http` | 自定义 HTTP，见下方契约 |

---

## 通用 HTTP 契约（`provider = "http"`）

### 提交句柄

```
POST {base_url}{submit_path}
Content-Type: application/json

{ "handle": "5-S2-1-1234567" }
```

### 查询 MMR

```
GET {base_url}{rating_path}
```

响应示例：

```json
{
  "mmr": 1607,
  "mmr_playlike": 2110
}
```

### Stub 模式

```json
{
  "5-S2-1-1234567": { "mmr": 1607, "mmr_playlike": 2110 }
}
```
