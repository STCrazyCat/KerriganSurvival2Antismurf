"""Main window parameter guide and first-time calibration instructions."""

from __future__ import annotations

import customtkinter as ctk

from antismurf.build_meta import MEMORY_SCAN_AVAILABLE


_HELP_TEXT = """
【顶部状态栏】
· 状态：当前是否在 KS2 房间、是否房主、地图名；空闲时显示内存扫描阶段与提示。
· Dry Run：勾选后只模拟踢人，不实际发送按键。
· 极高嫌疑自动踢：分数达到踢人阈值（默认 100）且为房主时自动踢出。

【大厅玩家列表 — 标准模式】
· 句柄：Battle.net 格式玩家 ID（如 5-S2-1-1234567），括号内为备注。
· 玩家ID：游戏内显示昵称；无昵称时显示 profile 数字 ID。
· MMR / Playlike：社区汇总 MMR 与反推 PL（Playlike）。
· 核心差：核心 MMR 与近期 PL 抬升的综合摘要（如 +800、3局+900）。
· 嫌疑 / 分数：规则引擎综合评分；低/中/高/极高 四档，阈值默认 20 / 60 / 100。
· 规则：触发的评分规则 ID（最多显示 3 条）。

【大厅玩家列表 — 列表模式（模式6）】
· 幸存MMR / 凯瑞甘MMR：核心 · 前三 · 均值 三段式展示。
· 幸存PL / 凯瑞甘PL：反推 PL 的前三 · 均值。
· 分：嫌疑分数；槽位：大厅位置编号。

【行内操作按钮】
· 详情 / 档案 / 战绩：查看评分详情、社区档案与近期对局。
· 踢出：房主可用，按 UI 校准的槽位执行右键菜单踢人。
· 标记+100：将句柄写入 handle_mark_rules，永久 +100 嫌疑分（高度疑似小号）。
· 白名单：加入数据库白名单，跳过评估、不再计分（与下方「信任 -20」不同）。
· 降级 / 黑名单：手动降分或加入黑名单规则。

【识别历史页】
· 记录每次扫描时的 MMR、PL、核心、嫌疑分等快照。
· 「对比刷新」拉取最新社区数据，显示 记录→当前 变化（如 MMR +120）。
· 高度疑似：同主界面「标记+100」。
· 白名单 -20：句柄匹配 handle_trust_rules，永久 -20 嫌疑分（信任玩家，仍参与评估）。

【评分规则说明】
· 表达式规则：基于 MMR、PL、场次、抬升等自动计分（balanced 预设）。
· 手动标记 +100 / 信任 -20：按句柄精确加减，写入 config/user.toml。

【初次使用 — UI 校准步骤】
1. 启动 StarCraft II，进入任意 KS2 自定义大厅（需能右键玩家槽位）。
2. 主界面点击「UI 校准」→「开始校准」。
3. 拖动准星到 1 号玩家槽中心 → 程序自动切到 SC2 并右键打开菜单。
4. 拖动准星到「移出房间 / Kick Player」菜单项 → 确定菜单偏移。
5. 依次确认 2~10 号槽位置（只需点槽位中心）。
6. 填写本机句柄（用于识别自己、录像路径等）→「保存并应用」。
7. 回到主界面点「测试识别」或在真实房间验证槽位与踢人菜单是否准确。
8. 取消 Dry Run 并按需开启「极高嫌疑自动踢」（建议先观察几局再开）。

【其他入口】
· 录像与积分：上传录像、查询 194823 社区积分与兑奖指令。
· 识别历史：跨局记住见过的玩家与 MMR 变化。
· 评分规则：调整表达式规则权重与阈值。
· 活动日志：评估与踢人记录。
"""


class HelpDialog(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title("使用说明")
        self.geometry("720x640")

        mode_hint = (
            "当前为内存模式6（列表模式列布局）。"
            if MEMORY_SCAN_AVAILABLE
            else "当前为标准列布局（OCR/混合模式）。"
        )
        ctk.CTkLabel(
            self,
            text=mode_hint,
            text_color="#888888",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 4))

        box = ctk.CTkTextbox(self, wrap="word", font=ctk.CTkFont(size=13))
        box.pack(fill="both", expand=True, padx=12, pady=8)
        box.insert("1.0", _HELP_TEXT.strip())
        box.configure(state="disabled")

        ctk.CTkButton(self, text="关闭", width=80, command=self.destroy).pack(
            pady=(0, 12)
        )
