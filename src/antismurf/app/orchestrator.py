from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Callable

from antismurf.actions.kicker import Kicker
from antismurf.community.factory import create_community_provider
from antismurf.config.settings import AppConfig
from antismurf.data.profile_builder import build_profile_from_community_raw
from antismurf.features import memory_scan_available
from antismurf.lobby.slot_tracker import SlotTracker
from antismurf.models.evaluation import MatchSummary, PlayerRecord
from antismurf.models.community import CommunityRating
from antismurf.models.player import PlayerHandle
from antismurf.replay.auto_upload import ReplayAutoUploader
from antismurf.replay.paths import resolve_replay_upload_paths
from antismurf.scoring.stage1_engine import Stage1Engine
from antismurf.scoring.same_match_detector import (
    SameMatchSpike,
    detect_kerrigan_same_match_spikes,
)
from antismurf.storage.store import PlayerStore

logger = logging.getLogger(__name__)

PlayerUpdateCallback = Callable[
    [dict[str, PlayerRecord], bool, str | None, bool, bool, bool], None
]


class Orchestrator:
    def __init__(
        self,
        config: AppConfig,
        on_update: PlayerUpdateCallback | None = None,
    ) -> None:
        from antismurf.config.settings import apply_memory_runtime_defaults

        config = apply_memory_runtime_defaults(config)
        self._config = config
        self._on_update = on_update
        self._tracker = SlotTracker()
        self._memory_reader = self._create_memory_reader()
        self._replay_uploader = ReplayAutoUploader(config)
        self._community = create_community_provider(config)
        self._engine = Stage1Engine(config)
        self._kicker = Kicker(config)
        self._store = PlayerStore("data/antismurf.db")
        self._players: dict[str, PlayerRecord] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._asyncio_loop: asyncio.AbstractEventLoop | None = None
        self._notified_handles: set[str] = set()
        self._last_memory_scan_at: float = 0.0
        self._is_local_host: bool = False
        self._local_handle: str | None = None
        self._host_rating: CommunityRating | None = None
        self._host_rating_handle: str | None = None
        self._lobby_active: bool = False
        self._lobby_map_name: str | None = None
        self._last_lobby_snapshot = None
        self._last_roster_status: dict[str, object] = {}
        self._same_match_notified: set[str] = set()
        self._last_manual_refresh_at: float = 0.0
        self._last_scan_error: str | None = None

    @property
    def is_local_host(self) -> bool:
        return self._is_local_host

    @property
    def players(self) -> dict[str, PlayerRecord]:
        return dict(self._players)

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def memory_enabled(self) -> bool:
        return memory_scan_available() and self._config.memory_enabled

    @property
    def memory_scan_available(self) -> bool:
        return memory_scan_available()

    @property
    def last_roster_status(self) -> dict[str, object]:
        return dict(self._last_roster_status)

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def last_scan_error(self) -> str | None:
        return self._last_scan_error

    @property
    def lobby_active(self) -> bool:
        return self._lobby_active

    def update_config(self, config: AppConfig) -> None:
        config.blocklist_handles |= self._config.blocklist_handles
        if not config.handle_mark_rules:
            config.handle_mark_rules = list(self._config.handle_mark_rules)
        if not config.handle_trust_rules:
            config.handle_trust_rules = list(self._config.handle_trust_rules)
        from antismurf.config.settings import apply_memory_runtime_defaults

        self._config = apply_memory_runtime_defaults(config)
        self._memory_reader = self._create_memory_reader()
        self._replay_uploader = ReplayAutoUploader(self._config)
        self._engine = Stage1Engine(self._config)
        self._kicker = Kicker(self._config)
        self._community = create_community_provider(self._config)

    async def start(self) -> None:
        await self._store.init()
        db_blocklist = await self._store.load_blocklist_handles()
        self._config.blocklist_handles |= db_blocklist
        self._asyncio_loop = asyncio.get_running_loop()
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception as exc:
                logger.exception("Orchestrator tick error: %s", exc)
            interval = (
                self._config.poll_interval_in_room_sec
                if self._lobby_active
                else self._config.poll_interval_sec
            )
            await asyncio.sleep(interval)

    async def _tick(self) -> None:
        await self._tick_mode6()

    async def _tick_mode6(self) -> None:
        if not self._config.memory_enabled or self._memory_reader is None:
            self._notify()
            return

        now = time.monotonic()
        in_room_hint = bool(self._last_roster_status.get("in_room"))
        scan_interval = (
            self._config.memory_scan_interval_in_room_sec
            if in_room_hint
            else min(self._config.memory_scan_interval_sec, 2.0)
        )
        due_scan = (
            now - self._last_memory_scan_at >= scan_interval
            or self._last_lobby_snapshot is None
        )

        if due_scan:
            await self._scan_lobby_snapshot()

        await self._process_lobby_snapshot()

    async def _scan_lobby_snapshot(self, force_reconfirm: bool = False) -> None:
        """立即扫描一次 SC2 大厅内存快照并更新缓存状态。

        force_reconfirm=True 时强制重新确认句柄位置(锚点失效时嗅探,
        已确认时用附近嗅探复核)——由手动刷新节流触发。
        """
        if self._memory_reader is None:
            return
        self._last_lobby_snapshot = await asyncio.to_thread(
            self._memory_reader.read_lobby_snapshot,
            force_reconfirm,
        )
        self._last_memory_scan_at = time.monotonic()
        state = self._memory_reader.roster_state
        self._last_roster_status = {
            "phase": state.phase,
            "in_room": state.in_room,
            "room_created": state.room_created,
            "record_base": state.record_base,
            "record_base_source": state.record_base_source,
            "member_count": state.member_count,
            "handle_location_state": state.handle_location_state,
            "handle_location_source": state.handle_location_source,
            "host_handle_address": state.host_handle_address,
            "roster_verified": state.roster_verified,
        }
        snap = self._last_lobby_snapshot
        self._last_scan_error = snap.error if snap else None
        if snap and snap.local_handle:
            if snap.local_handle != self._local_handle:
                self._local_handle = snap.local_handle
                await self._refresh_host_rating()
            self._replay_uploader.set_local_handle(snap.local_handle)

    async def _refresh_host_rating(self) -> None:
        """获取主机(房主)自身战绩,用于与玩家做同局匹配。"""
        handle = self._local_handle
        if not handle:
            self._host_rating = None
            self._host_rating_handle = None
            return
        if handle == self._host_rating_handle and self._host_rating is not None:
            return
        try:
            await self._community.submit_handle(handle)
            rating = await self._community.get_rating_by_handle(handle)
        except Exception as exc:
            logger.warning("Failed to fetch host rating for %s: %s", handle, exc)
            rating = None
        self._host_rating_handle = handle
        self._host_rating = rating

    async def _process_lobby_snapshot(self) -> None:
        snapshot = self._last_lobby_snapshot
        if snapshot is None:
            if self._replay_uploader.should_run_check():
                await self._check_replay_upload()
            self._notify()
            return

        if snapshot.error and not snapshot.handles:
            if self._replay_uploader.should_run_check():
                await self._check_replay_upload()
            self._notify()
            return

        in_room = bool(self._last_roster_status.get("in_room"))

        if in_room:
            if not self._lobby_active:
                self._lobby_active = True
                if self._memory_reader is not None:
                    self._memory_reader.set_lobby_active(True)
                self._lobby_map_name = snapshot.map_name or (
                    self._config.target_maps[0]
                    if self._config.target_maps
                    else "凯瑞甘生存2"
                )
                self._tracker.reset()
                self._replay_uploader.on_lobby_enter()
                logger.info(
                    "Mode6 in_room: base=%s members=%s",
                    self._last_roster_status.get("record_base"),
                    len(snapshot.handles),
                )

            self._is_local_host = snapshot.is_local_host
            self._local_handle = snapshot.local_handle
            slots = snapshot.handles
            if self._replay_uploader.should_run_check():
                await self._check_replay_upload()
            joined, left = self._tracker.diff(slots)
            if joined or left:
                logger.info(
                    "Lobby presence: +%s -%s (room=%s)",
                    [p.handle for p in joined],
                    left,
                    [p.handle for p in slots],
                )
            self._remove_departed_players(slots, left)
            self._sync_lobby_placeholders(slots)

            to_process: dict[str, PlayerHandle] = {
                player.handle: player for player in joined if player.handle
            }
            for player in slots:
                if player.handle and player.handle not in self._players:
                    to_process[player.handle] = player

            for player in to_process.values():
                player = self._enrich_display_name(player)
                if not player.handle:
                    continue
                if await self._store.is_whitelisted(player.handle):
                    self._players[player.handle] = PlayerRecord(
                        handle=player.handle,
                        slot_index=player.slot_index,
                        discriminator=player.discriminator,
                        profile_id=player.profile_id,
                        profile_ref=player.profile_ref,
                        display_name=player.display_name,
                        team_name=player.team_name or "",
                        remark=self._lookup_remark(player.handle),
                        tier="low",
                        score=0,
                        whitelisted=True,
                    )
                    continue
                await self._process_player(player)
        elif self._lobby_active:
            self._on_lobby_exit()
            if self._memory_reader is not None:
                self._memory_reader.set_lobby_active(False)
            self._replay_uploader.on_lobby_exit()
            self._lobby_active = False
            await self._check_replay_upload()
            self._notify()
            return

        if self._replay_uploader.should_run_check():
            await self._check_replay_upload()
        self._notify()

    async def refresh_lobby_now(self, *, force: bool = False) -> bool:
        """手动刷新:立即扫描一次房间并重新评估玩家。

        已确认句柄位置时仅重新读取(不嗅探);若用户在 1.5 秒内多次刷新
        或显式 force,则强制重新确认句柄位置(触发附近嗅探复核)。
        """
        if not self._config.memory_enabled or self._memory_reader is None:
            return False
        now = time.monotonic()
        rapid = (
            now - self._last_manual_refresh_at
            < self._config.memory_handle_reconfirm_threshold_sec
        )
        self._last_manual_refresh_at = now
        await self._scan_lobby_snapshot(force_reconfirm=force or rapid)
        await self._process_lobby_snapshot()
        return True

    async def _check_replay_upload(self) -> None:
        results = await asyncio.to_thread(self._replay_uploader.check_and_upload)
        if not results:
            return
        uploaded = [result.path.name for result in results if result.ok]
        if uploaded:
            logger.info("Auto-uploaded KS replays: %s", ", ".join(uploaded))
        for result in results:
            if not result.ok and result.error:
                logger.warning(
                    "Replay upload skipped/failed for %s: %s",
                    result.path.name,
                    result.error,
                )

    def _on_lobby_exit(self) -> None:
        self._players.clear()
        self._tracker.reset()
        self._notified_handles.clear()
        self._last_lobby_snapshot = None
        self._is_local_host = False
        self._lobby_active = False
        self._lobby_map_name = None
        self._host_rating = None
        self._host_rating_handle = None
        self._same_match_notified.clear()

    def _sync_lobby_placeholders(self, slots: list[PlayerHandle]) -> None:
        for player in slots:
            if not player.handle:
                continue
            enriched = self._enrich_display_name(player)
            existing = self._players.get(enriched.handle)
            if existing is not None:
                existing.slot_index = enriched.slot_index
                if enriched.profile_id is not None:
                    existing.profile_id = enriched.profile_id
                if enriched.display_name:
                    existing.display_name = enriched.display_name
                if enriched.team_name:
                    existing.team_name = enriched.team_name
                continue
            self._players[enriched.handle] = PlayerRecord(
                handle=enriched.handle,
                slot_index=enriched.slot_index,
                discriminator=enriched.discriminator,
                profile_id=enriched.profile_id,
                profile_ref=enriched.profile_ref,
                display_name=enriched.display_name or "",
                team_name=enriched.team_name or "",
                remark=self._lookup_remark(enriched.handle),
                tier="low",
                score=0,
                triggered_rules=[],
                rule_reasons=[],
            )

    def _remove_departed_players(
        self,
        slots: list[PlayerHandle],
        left: list[str],
    ) -> None:
        current_handles = {player.handle for player in slots if player.handle}
        departed = set(left) | {
            handle for handle in self._players if handle not in current_handles
        }
        for handle in departed:
            self._players.pop(handle, None)
            self._notified_handles.discard(handle)

        for handle, record in self._players.items():
            if handle not in current_handles:
                continue
            for player in slots:
                if player.handle == handle:
                    record.slot_index = player.slot_index
                    if player.profile_id is not None:
                        record.profile_id = player.profile_id
                    enriched = self._enrich_display_name(player)
                    if enriched.display_name:
                        record.display_name = enriched.display_name
                    if enriched.team_name:
                        record.team_name = enriched.team_name
                    record.remark = self._lookup_remark(handle)
                    break

    def _enrich_display_name(self, player: PlayerHandle) -> PlayerHandle:
        return player

    def _lookup_remark(self, handle: str) -> str:
        return ""

    async def _process_player(
        self,
        player: PlayerHandle,
        match_history: list[MatchSummary] | None = None,
    ) -> None:
        if not player.handle:
            return
        player = self._enrich_display_name(player)
        await self._community.submit_handle(player.handle)
        community = await self._community.get_rating_by_handle(player.handle)
        spike_hits = self._detect_same_match_spikes(player.handle, community)
        existing = self._players.get(player.handle)
        history = match_history or (existing.match_history if existing else None)
        result = self._engine.evaluate(
            player.handle,
            player.slot_index,
            community,
            match_history=history or None,
            blocklisted=player.handle in self._config.blocklist_handles,
            has_team=bool(player.team_name and player.team_name.strip()),
            handle_resolved=bool(player.handle),
            handle_ambiguous=player.handle_ambiguous,
            handle_candidate_count=player.handle_candidate_count,
            handle_constructed=player.handle_constructed,
            handle_from_binding=player.handle_from_binding,
            ocr_digit_obfuscation=player.ocr_digit_obfuscation,
            kerrigan_same_match_spike_count=len(spike_hits),
        )
        await self._store.log_evaluation(
            result.handle, result.tier, result.score, result.triggered_rules
        )
        record = PlayerRecord(
            handle=result.handle,
            slot_index=result.slot_index,
            discriminator=result.handle_discriminator,
            profile_id=player.profile_id or result.handle_discriminator,
            profile_ref=player.profile_ref,
            display_name=player.display_name or "",
            team_name=player.team_name or "",
            remark=self._lookup_remark(result.handle),
            tier=result.tier,
            score=result.score,
            triggered_rules=result.triggered_rules,
            rule_reasons=result.rule_reasons,
            community=result.community,
            match_history=history or [],
            whitelisted=existing.whitelisted if existing else False,
            first_seen_at=existing.first_seen_at if existing else datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self._players[result.handle] = record
        await self._store.upsert_player_sighting(record)
        if spike_hits and result.handle not in self._same_match_notified:
            self._same_match_notified.add(result.handle)
            per = self._config.same_match_kerrigan_spike_score
            from antismurf.utils.notify import notify

            notify(
                "AntiSmurf 窥屏者识别：同局凯瑞甘MMR异常",
                f"嫌疑对象: {result.handle}\n"
                f"次数: {len(spike_hits)} 次\n"
                f"原因: 与主机同一对局时凯瑞甘阵营 MMR 异常升高"
                f" (+{per:.0f}/次)",
            )
        if self._is_local_host and not (
            self._local_handle and result.handle == self._local_handle
        ):
            if self._config.whitelist_mode:
                # 白名单模式:仅保留白名单玩家,其余自动踢出
                should_kick = not self._is_trusted_handle(result.handle)
            else:
                should_kick = self._engine.should_auto_kick(result)
            if should_kick:
                ok = self._kicker.kick_slot(result.slot_index)
                await self._store.log_kick(result.handle, ok, self._config.dry_run)
        if result.tier in ("high", "critical"):
            self.on_high_suspicion(result.handle, result.tier, result.score)

    def _is_trusted_handle(self, handle: str) -> bool:
        """是否命中 handle_trust_rules(白名单-20,白名单模式下不被踢)。"""
        return any(trust.handle == handle for trust in self._config.handle_trust_rules)

    def _detect_same_match_spikes(
        self,
        handle: str,
        community: CommunityRating,
    ) -> list[SameMatchSpike]:
        """检测玩家与主机同局时的凯瑞甘 MMR 异常升高(无主机数据时返回空)。"""
        host = self._host_rating
        if host is None or host.profile is None:
            return []
        profile = community.profile
        if profile is None:
            profile = build_profile_from_community_raw(handle, community.raw)
        if profile is None or not profile.playlike_games:
            return []
        return detect_kerrigan_same_match_spikes(
            profile,
            host.profile,
            threshold=self._config.same_match_kerrigan_spike_threshold,
        )

    def _notify(self) -> None:
        if self._on_update:
            active = self._lobby_active
            map_name = self._lobby_map_name
            self._on_update(
                self._players,
                active,
                map_name,
                self._is_local_host,
                False,
                False,
            )

    def set_sc2_target_pid(self, pid: int | None) -> None:
        self._config.memory_target_pid = int(pid or 0)
        if self._memory_reader is not None:
            self._memory_reader.reset_session()
        self._last_lobby_snapshot = None
        self._last_memory_scan_at = 0.0
        self._last_roster_status = {}
        self._last_scan_error = None
        self._host_rating = None
        self._host_rating_handle = None
        logger.info("SC2 target pid set to %s", pid or "auto")

    def _create_memory_reader(self):
        if not memory_scan_available():
            return None
        from antismurf.lobby.memory_lobby_reader import MemoryLobbyReader

        return MemoryLobbyReader(
            self._config,
        )

    def reload_rules_pack(self) -> str | None:
        path = (self._config.rules_pack_path or "").strip()
        if not path:
            return "未配置规则包路径"
        from pathlib import Path

        from antismurf.scoring.rule_pack import load_rule_pack

        file_path = Path(path)
        if not file_path.is_file():
            return f"规则包不存在: {path}"
        try:
            _, rules = load_rule_pack(file_path)
            self._config.expression_rules = rules
            self._engine = Stage1Engine(self._config)
            logger.info("Loaded %s rules from %s", len(rules), path)
            return None
        except Exception as exc:
            return str(exc)

    def kick_player(self, handle: str) -> bool:
        if not self._is_local_host:
            logger.info("Kick blocked: local user is not the lobby host")
            return False
        record = self._players.get(handle)
        if not record:
            return False
        if self._local_handle and handle == self._local_handle:
            logger.info("Kick blocked: cannot kick local player %s", handle)
            return False
        ok = self._kicker.kick_slot(record.slot_index)
        if self._asyncio_loop:
            asyncio.run_coroutine_threadsafe(
                self._store.log_kick(handle, ok, self._config.dry_run),
                self._asyncio_loop,
            )
        return ok

    def fetch_evaluation_logs_sync(self, limit: int = 100):
        if not self._asyncio_loop:
            return []
        future = asyncio.run_coroutine_threadsafe(
            self._store.list_evaluations(limit), self._asyncio_loop
        )
        try:
            return future.result(timeout=5)
        except Exception:
            return []

    def fetch_kick_logs_sync(self, limit: int = 50):
        if not self._asyncio_loop:
            return []
        future = asyncio.run_coroutine_threadsafe(
            self._store.list_kicks(limit), self._asyncio_loop
        )
        try:
            return future.result(timeout=5)
        except Exception:
            return []

    async def whitelist_player(self, handle: str) -> None:
        await self._store.add_whitelist(handle)
        if handle in self._players:
            self._players[handle].whitelisted = True
            self._players[handle].tier = "low"
        self._notify()

    async def whitelist_handles(self, handles: list[str]) -> int:
        """批量添加白名单,返回实际新增数量(已存在的跳过)。"""
        added = 0
        for handle in handles:
            handle = handle.strip()
            if not handle or await self._store.is_whitelisted(handle):
                continue
            await self.whitelist_player(handle)
            added += 1
        return added

    async def blocklist_player(self, handle: str) -> None:
        await self._store.add_blocklist(handle)
        self._config.blocklist_handles.add(handle)
        if handle in self._players:
            await self.re_evaluate_player(handle)
        self._notify()

    async def mark_player_handle(
        self,
        handle: str,
        *,
        weight: float = 100.0,
        label: str = "",
    ) -> None:
        from antismurf.config.settings import HandleMarkRule, save_user_config

        handle = handle.strip()
        if not handle:
            return
        for mark in self._config.handle_mark_rules:
            if mark.handle == handle:
                return
        mark_label = label or f"手动标记 {handle}"
        self._config.handle_mark_rules.append(
            HandleMarkRule(
                handle=handle,
                weight=weight,
                label=mark_label,
            )
        )
        save_user_config(self._config)
        if handle in self._players:
            await self.re_evaluate_player(handle)
        self._notify()

    async def blacklist_and_mark(self, handle: str, weight: float = 200.0) -> None:
        """一键拉黑:加入黑名单列表并写入 handle_mark_rules(+200 嫌疑分)。"""
        handle = handle.strip()
        if not handle:
            return
        await self._store.add_blocklist(handle)
        self._config.blocklist_handles.add(handle)
        await self.mark_player_handle(
            handle, weight=weight, label=f"一键拉黑 {handle}"
        )

    def on_high_suspicion(self, handle: str, tier: str, score: float) -> None:
        if not self._config.notify_high_suspicion:
            return
        if handle in self._notified_handles:
            return
        self._notified_handles.add(handle)
        from antismurf.utils.notify import notify

        notify(
            "AntiSmurf 高嫌疑玩家",
            f"{handle}\n等级: {tier}  分数: {score:.0f}",
        )

    def preview_recognition(self) -> dict:
        preview = (
            self._memory_reader.preview()
            if self._memory_reader is not None
            else {}
        )
        preview["memory_enabled"] = self.memory_enabled
        preview["memory_scan_available"] = memory_scan_available()
        preview["local_handle"] = self._local_handle
        preview["replay_upload"] = self._replay_uploader.preview()
        preview["replay_search_paths"] = resolve_replay_upload_paths(
            self._config.replays_paths,
            self._local_handle or self._config.host_handle or None,
        )
        return preview

    def refresh_replays_sync(self) -> dict:
        preview = self._replay_uploader.preview()
        latest = self._replay_uploader.latest_candidate_path()
        preview["latest_candidate"] = str(latest) if latest else None
        return preview

    def upload_replays_now_sync(self) -> list[dict]:
        results = self._replay_uploader.upload_now()
        return [
            {
                "path": str(item.path),
                "name": item.path.name,
                "ok": item.ok,
                "error": item.error,
                "status_code": item.status_code,
            }
            for item in results
        ]

    def fetch_player_sightings_sync(self, limit: int = 200):
        if not self._asyncio_loop:
            return []
        future = asyncio.run_coroutine_threadsafe(
            self._store.list_player_sightings(limit), self._asyncio_loop
        )
        try:
            return future.result(timeout=5)
        except Exception:
            return []

    def marked_handles(self) -> set[str]:
        return {
            mark.handle
            for mark in self._config.handle_mark_rules
            if mark.enabled
        }

    def trusted_handles(self) -> set[str]:
        return {
            rule.handle
            for rule in self._config.handle_trust_rules
            if rule.enabled
        }

    async def fetch_sighting_comparisons(self, limit: int = 200):
        from antismurf.data.player_display import sighting_snapshot_from_community
        from antismurf.data.sighting_compare import compare_sighting

        entries = await self._store.list_player_sightings(limit)
        results = []
        for entry in entries:
            try:
                await self._community.submit_handle(entry.handle)
                community = await self._community.get_rating_by_handle(entry.handle)
                current = sighting_snapshot_from_community(entry.handle, community)
                results.append(compare_sighting(entry, current))
            except Exception as exc:
                logger.warning(
                    "Sighting comparison failed for %s: %s", entry.handle, exc
                )
                results.append(
                    compare_sighting(entry, None, fetch_error=str(exc))
                )
        return results

    def fetch_sighting_comparisons_sync(self, limit: int = 200):
        if not self._asyncio_loop:
            return []
        future = asyncio.run_coroutine_threadsafe(
            self.fetch_sighting_comparisons(limit), self._asyncio_loop
        )
        try:
            return future.result(timeout=120)
        except Exception:
            return []

    async def trust_player_handle(
        self,
        handle: str,
        *,
        weight: float = -20.0,
        label: str = "",
    ) -> None:
        from antismurf.config.settings import HandleTrustRule, save_user_config

        handle = handle.strip()
        if not handle:
            return
        for rule in self._config.handle_trust_rules:
            if rule.handle == handle:
                return
        trust_label = label or f"信任白名单 {handle}"
        self._config.handle_trust_rules.append(
            HandleTrustRule(
                handle=handle,
                weight=weight,
                label=trust_label,
            )
        )
        save_user_config(self._config)
        if handle in self._players:
            await self.re_evaluate_player(handle)
        self._notify()

    def get_match_history_sync(self, handle: str):
        return []

    async def re_evaluate_player(self, handle: str) -> None:
        record = self._players.get(handle)
        if not record:
            return
        player = PlayerHandle(
            handle=handle,
            slot_index=record.slot_index,
            display_text=handle,
            display_name=record.display_name,
            discriminator=record.discriminator,
            profile_id=record.profile_id,
            profile_ref=record.profile_ref,
        )
        await self._process_player(player, match_history=record.match_history)

    async def downgrade_player(self, handle: str) -> None:
        record = self._players.get(handle)
        if not record:
            return
        record.tier = "low"
        record.score = 0.0
        record.updated_at = datetime.now(timezone.utc)
        self._notify()

    def set_player_history(self, handle: str, matches: list[MatchSummary]) -> None:
        if handle not in self._players:
            return
        self._players[handle].match_history = matches
        if self._asyncio_loop:
            asyncio.run_coroutine_threadsafe(
                self.re_evaluate_player(handle), self._asyncio_loop
            )
        else:
            self._notify()

    def get_profile_ref_sync(self, handle: str) -> tuple[int, int, int] | None:
        if not self._asyncio_loop:
            return None
        future = asyncio.run_coroutine_threadsafe(
            self._store.get_profile_ref(handle), self._asyncio_loop
        )
        try:
            return future.result(timeout=5)
        except Exception:
            return None

    def save_profile_ref_sync(
        self, handle: str, region_id: int, realm_id: int, profile_id: int
    ) -> None:
        if not self._asyncio_loop:
            return
        asyncio.run_coroutine_threadsafe(
            self._store.save_profile_ref(
                handle, region_id, realm_id, profile_id
            ),
            self._asyncio_loop,
        )
