from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


def _project_root() -> Path:
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def _bundled_config_root() -> Path:
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return _project_root()


@dataclass
class RuleConfig:
    enabled: bool = True
    threshold: float = 0.0
    weight: float = 0.0


@dataclass
class ExpressionRule:
    id: str
    enabled: bool = True
    label: str = ""
    left: str = ""
    arith_op: str = ""
    middle: str = ""
    op: str = ">="
    right: str | float | bool = ""
    right2: str | float | bool = ""
    weight: float = 0.0
    else_weight: float = 0.0
    min_games: int = 0


@dataclass
class HandleMarkRule:
    """Manual per-handle score bonus (quick mark from player row)."""

    handle: str
    weight: float = 100.0
    label: str = ""
    enabled: bool = True


@dataclass
class HandleTrustRule:
    """Manual per-handle score reduction (whitelist trust from history row)."""

    handle: str
    weight: float = -20.0
    label: str = ""
    enabled: bool = True


@dataclass
class AppConfig:
    # 分数显示颜色(主界面/历史界面,可在设置中修改)
    score_color_positive: str = "#ff5c5c"  # +分(嫌疑)红色
    score_color_negative: str = "#57d957"  # -分(信任)绿色
    score_color_zero: str = "#ffffff"      # 0 分(中性)白色

    # 嫌疑提示字体颜色:疑似小号 / 黑名单 / 非白名单(对应模式下)玩家名称着色
    suspect_name_color: str = "#ff5c5c"    # 默认红色

    # 同局凯瑞甘 MMR 异常检测(识别窥屏者:与主机同局时评估 MMR 异常升高)
    same_match_kerrigan_spike_threshold: float = 400.0  # 异常升高阈值(反推核心−凯瑞甘核心)
    same_match_kerrigan_spike_score: float = 20.0  # 每次异常加分

    # AI 助手(规则编写,OpenAI 兼容接口)
    ai_api_base_url: str = "https://api.deepseek.com/v1"
    ai_api_key: str = ""
    ai_model: str = "deepseek-chat"

    # 白名单模式:自动踢出白名单以外的所有玩家(默认黑名单模式)
    whitelist_mode: bool = False

    target_maps: list[str] = field(
        default_factory=lambda: ["凯瑞甘生存2", "Kerrigan Survival 2"]
    )
    poll_interval_sec: float = 2.5
    poll_interval_in_room_sec: float = 0.35
    kick_threshold: float = 100.0
    tier_medium: float = 20.0
    tier_high: float = 60.0
    tier_critical: float = 100.0
    rules: dict[str, RuleConfig] = field(default_factory=dict)
    expression_rules: list[ExpressionRule] = field(default_factory=list)
    handle_mark_rules: list[HandleMarkRule] = field(default_factory=list)
    handle_trust_rules: list[HandleTrustRule] = field(default_factory=list)
    scoring_preset: str = "balanced"
    dry_run: bool = True
    auto_kick_enabled: bool = False
    kick_cooldown_sec: float = 5.0
    kick_menu_labels: list[str] = field(
        default_factory=lambda: ["移除玩家", "Kick Player", "踢出玩家"]
    )
    kick_menu_down_presses: int = 1
    kick_menu_template_path: str = "target/kick_menu.png"
    kick_fast_path: bool = True
    kick_ocr_fallback: bool = False
    kick_menu_open_wait_sec: float = 0.12
    kick_focus_wait_sec: float = 0.12
    kick_save_debug_shots: bool = False
    kick_menu_remove_region: dict[str, float] = field(default_factory=dict)
    kick_menu_offset: dict[str, float] = field(default_factory=dict)
    kick_slot_step: dict[str, float] = field(default_factory=dict)
    profile_menu_labels: list[str] = field(
        default_factory=lambda: [
            "查看档案",
            "View Profile",
            "查看个人档案",
            "Profile",
        ]
    )
    profile_menu_down_presses: int = 0
    community_stub_path: str = "config/community_stub.json"
    community_provider: str = "disabled"
    community_base_url: str = ""
    community_submit_path: str = "/api/v1/handles"
    community_rating_path: str = "/api/v1/handles/{handle}"
    community_api_key: str = ""
    community_timeout_sec: float = 10.0
    window_title_contains: str = "StarCraft II"
    slot_regions: list[dict[str, float]] = field(default_factory=list)
    slot_id_regions: list[dict[str, float]] = field(default_factory=list)
    map_region: dict[str, float] = field(
        default_factory=lambda: {"x": 0.35, "y": 0.02, "w": 0.30, "h": 0.05}
    )
    host_handle: str = ""
    blocklist_handles: set[str] = field(default_factory=set)
    notify_high_suspicion: bool = True
    vision_enabled: bool = True
    vision_engine: str = "paddleocr"
    vision_use_gpu: bool = False
    vision_scan_interval_sec: float = 3.0
    vision_min_confidence: float = 0.5
    vision_save_debug_images: bool = False
    memory_enabled: bool = False
    memory_process_names: tuple[str, ...] = ("SC2_x64.exe", "SC2.exe")
    memory_chunk_size: int = 65536
    memory_handle_scan_budget_sec: float = 12.0
    memory_name_search_radius: int = 768
    memory_scan_interval_sec: float = 5.0
    memory_scan_interval_in_room_sec: float = 0.35
    memory_record_enabled: bool = True
    memory_targeted_scan_enabled: bool = True
    memory_targeted_region_limit: int = 24
    memory_targeted_min_regions: int = 2
    memory_targeted_min_handles: int = 2
    memory_full_scan_fallback: bool = True
    memory_host_handle_module_offset: int = 0x3E2F340
    memory_host_anchor_scan_radius: int = 8192
    memory_host_anchor_enabled: bool = True
    memory_host_anchor_sniff_enabled: bool = True
    memory_handle_reconfirm_threshold_sec: float = 1.5
    memory_scan_mode: str = "roster"
    memory_calibration_path: str = "data/probe_calibration.json"
    memory_roster_rescan_budget_sec: float = 5.0
    memory_roster_rescan_every_scans: int = 6
    memory_roster_rescan_every_scans_in_room: int = 24
    memory_target_pid: int = 0
    memory_list_only: bool = True
    memory_auto_enter_lobby: bool = True
    replays_enabled: bool = True
    replays_max_count: int = 100
    replays_refresh_sec: float = 60.0
    replays_paths: list[str] = field(default_factory=list)
    replays_ks2_only: bool = True
    replays_map_prefixes: tuple[str, ...] = (
        "凯瑞甘生存2",
        "Kerrigan Survival",
        "凯瑞甘生存",
    )
    replays_filename_priorities: tuple[str, ...] = (
        "凯瑞甘生存2",
        "凯瑞甘生存",
        "Kerrigan Survival",
    )
    replay_upload_enabled: bool = True
    replay_upload_url: str = "https://replay.kerrigansurvival.com/upload"
    replay_upload_user_agent: str = "kerrigan-survival-uploader/1.07"
    replay_upload_max_bytes: int = 3 * 1024 * 1024
    replay_upload_min_age_sec: float = 5.0
    replay_upload_grace_sec: float = 120.0
    replay_upload_timeout_sec: float = 60.0
    replay_upload_ks2_only: bool = True
    replay_upload_window_hours: float = 48.0
    replay_upload_check_interval_sec: float = 300.0
    replay_upload_grace_check_interval_sec: float = 5.0
    replay_upload_filename_markers: tuple[str, ...] = (
        "凯瑞甘生存2",
        "凯瑞甘生存",
        "Kerrigan Survival",
    )
    replay_upload_use_filename_filter: bool = True
    roster_enabled: bool = False
    roster_sync_interval_sec: float = 300.0
    roster_sync_provider: str = "disabled"
    roster_sync_path: str = "config/player_roster.xlsx"
    roster_sync_url: str = ""
    roster_sync_push_enabled: bool = True
    roster_sync_push_from_replays: bool = True
    roster_former_name_prefix: str = "曾用名"
    roster_sync_fetch_url: str = ""
    roster_sync_push_url: str = ""
    roster_sync_api_key: str = ""
    rules_pack_path: str = ""
    data_sources_confirmed: bool = False


def load_config(path: Path | None = None) -> AppConfig:
    root = _project_root()
    bundled = _bundled_config_root()
    config_path = path or bundled / "config" / "default.toml"
    if not config_path.exists():
        config_path = root / "config" / "default.toml"
    user_path = root / "config" / "user.toml"
    data: dict[str, Any] = {}
    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)
    if user_path.exists():
        with open(user_path, "rb") as f:
            user_data = tomllib.load(f)
        data = _deep_merge(data, user_data)

    rules: dict[str, RuleConfig] = {}
    for name, rule_data in data.get("rules", {}).items():
        if isinstance(rule_data, dict):
            rules[name] = RuleConfig(
                enabled=rule_data.get("enabled", True),
                threshold=float(rule_data.get("threshold", 0)),
                weight=float(rule_data.get("weight", 0)),
            )

    actions = data.get("actions", {})
    polling = data.get("polling", {})
    scoring = data.get("scoring", {})
    community = data.get("community", {})
    expression_rules = _load_expression_rules(scoring, data)
    handle_mark_rules = _load_handle_mark_rules(scoring)
    handle_trust_rules = _load_handle_trust_rules(scoring)
    scoring_preset = str(scoring.get("preset", "balanced"))
    target = data.get("target_maps", {})
    ui = data.get("ui", {})
    calibration = data.get("calibration", {})
    vision = data.get("vision", {})
    memory = data.get("memory", {})
    replays = data.get("replays", {})
    replay_upload = data.get("replay_upload", {})
    roster = data.get("roster", {})
    roster_sync = roster.get("sync", {}) if isinstance(roster.get("sync"), dict) else {}
    data_sources = data.get("data_sources", {})
    ai = data.get("ai", {})
    if not isinstance(ai, dict):
        ai = {}

    blocklist_path = root / "config" / "blocklist.txt"
    blocklist_handles = _load_blocklist_file(blocklist_path)

    stub = community.get("stub_path", "config/community_stub.json")
    if not Path(stub).is_absolute():
        user_stub = root / stub
        if user_stub.exists():
            stub = str(user_stub)
        elif (bundled / stub).exists():
            stub = str(bundled / stub)
        else:
            stub = str(root / stub)

    return AppConfig(
        target_maps=list(target.get("names", ["凯瑞甘生存2", "Kerrigan Survival 2"])),
        poll_interval_sec=float(polling.get("interval_sec", 2.5)),
        poll_interval_in_room_sec=float(polling.get("interval_in_room_sec", 0.35)),
        kick_threshold=float(scoring.get("kick_threshold", 100)),
        tier_medium=float(scoring.get("tier_medium", 20)),
        tier_high=float(scoring.get("tier_high", 60)),
        tier_critical=float(scoring.get("tier_critical", 100)),
        rules=rules,
        expression_rules=expression_rules,
        handle_mark_rules=handle_mark_rules,
        handle_trust_rules=handle_trust_rules,
        scoring_preset=scoring_preset,
        dry_run=bool(actions.get("dry_run", True)),
        auto_kick_enabled=bool(actions.get("auto_kick_enabled", False)),
        whitelist_mode=bool(actions.get("whitelist_mode", False)),
        kick_cooldown_sec=float(actions.get("kick_cooldown_sec", 5)),
        kick_menu_labels=list(
            actions.get("kick_menu_labels", ["移除玩家", "Kick Player"])
        ),
        kick_menu_down_presses=int(actions.get("kick_menu_down_presses", 1)),
        kick_menu_template_path=str(
            actions.get("kick_menu_template_path", "target/kick_menu.png")
        ),
        kick_fast_path=bool(actions.get("kick_fast_path", True)),
        kick_ocr_fallback=bool(actions.get("kick_ocr_fallback", False)),
        kick_menu_open_wait_sec=float(actions.get("kick_menu_open_wait_sec", 0.12)),
        kick_focus_wait_sec=float(actions.get("kick_focus_wait_sec", 0.12)),
        kick_save_debug_shots=bool(actions.get("kick_save_debug_shots", False)),
        kick_menu_remove_region=dict(calibration.get("kick_menu_remove_region", {})),
        kick_menu_offset=dict(calibration.get("kick_menu_offset", {})),
        kick_slot_step=dict(calibration.get("kick_slot_step", {})),
        profile_menu_labels=list(
            actions.get(
                "profile_menu_labels",
                ["查看档案", "View Profile", "查看个人档案", "Profile"],
            )
        ),
        profile_menu_down_presses=int(actions.get("profile_menu_down_presses", 0)),
        community_stub_path=stub,
        community_provider=str(community.get("provider", "disabled")),
        community_base_url=str(community.get("base_url", "")),
        community_submit_path=str(
            community.get("submit_path", "/api/v1/handles")
        ),
        community_rating_path=str(
            community.get("rating_path", "/api/v1/handles/{handle}")
        ),
        community_api_key=str(community.get("api_key", "")),
        community_timeout_sec=float(community.get("timeout_sec", 10)),
        window_title_contains=str(ui.get("window_title_contains", "StarCraft II")),
        slot_regions=list(calibration.get("slot_regions", [])),
        slot_id_regions=list(calibration.get("slot_id_regions", [])),
        map_region=dict(
            calibration.get(
                "map_region",
                {"x": 0.35, "y": 0.02, "w": 0.30, "h": 0.05},
            )
        ),
        host_handle=str(data.get("host", {}).get("handle", "")),
        blocklist_handles=blocklist_handles,
        notify_high_suspicion=bool(ui.get("notify_high_suspicion", True)),
        ai_api_base_url=str(ai.get("base_url", "https://api.deepseek.com/v1")),
        ai_api_key=str(ai.get("api_key", "")),
        ai_model=str(ai.get("model", "deepseek-chat")),
        vision_enabled=bool(vision.get("enabled", True)),
        vision_engine=str(vision.get("engine", "paddleocr")),
        vision_use_gpu=bool(vision.get("use_gpu", False)),
        vision_scan_interval_sec=float(vision.get("scan_interval_sec", 3.0)),
        vision_min_confidence=float(vision.get("min_confidence", 0.5)),
        vision_save_debug_images=bool(vision.get("save_debug_images", False)),
        memory_enabled=bool(memory.get("enabled", False)),
        memory_process_names=tuple(
            str(name)
            for name in memory.get("process_names", ["SC2_x64.exe", "SC2.exe"])
        ),
        memory_chunk_size=int(memory.get("chunk_size", 65536)),
        memory_handle_scan_budget_sec=float(
            memory.get("handle_scan_budget_sec", 12.0)
        ),
        memory_name_search_radius=int(memory.get("name_search_radius", 768)),
        memory_scan_interval_sec=float(memory.get("scan_interval_sec", 5.0)),
        memory_scan_interval_in_room_sec=float(
            memory.get("scan_interval_in_room_sec", 0.35)
        ),
        memory_record_enabled=bool(memory.get("record_enabled", True)),
        memory_targeted_scan_enabled=bool(memory.get("targeted_scan_enabled", True)),
        memory_targeted_region_limit=int(memory.get("targeted_region_limit", 24)),
        memory_targeted_min_regions=int(memory.get("targeted_min_regions", 2)),
        memory_targeted_min_handles=int(memory.get("targeted_min_handles", 2)),
        memory_full_scan_fallback=bool(memory.get("full_scan_fallback", True)),
        memory_host_handle_module_offset=int(
            memory.get("host_handle_module_offset", "0x3E2F340"),
            0,
        ),
        memory_host_anchor_scan_radius=int(memory.get("host_anchor_scan_radius", 8192)),
        memory_host_anchor_enabled=bool(memory.get("host_anchor_enabled", True)),
        memory_host_anchor_sniff_enabled=bool(
            memory.get("host_anchor_sniff_enabled", True)
        ),
        memory_handle_reconfirm_threshold_sec=float(
            memory.get("handle_reconfirm_threshold_sec", 1.5)
        ),
        memory_scan_mode=str(memory.get("scan_mode", "roster")),
        memory_calibration_path=str(
            memory.get("calibration_path", "data/probe_calibration.json")
        ),
        memory_roster_rescan_budget_sec=float(
            memory.get("roster_rescan_budget_sec", 5.0)
        ),
        memory_roster_rescan_every_scans=int(
            memory.get("roster_rescan_every_scans", 6)
        ),
        memory_roster_rescan_every_scans_in_room=int(
            memory.get("roster_rescan_every_scans_in_room", 24)
        ),
        memory_target_pid=int(memory.get("target_pid", 0)),
        memory_list_only=bool(memory.get("list_only", True)),
        memory_auto_enter_lobby=bool(memory.get("auto_enter_lobby", True)),
        replays_enabled=bool(replays.get("enabled", True)),
        replays_max_count=int(replays.get("max_count", 100)),
        replays_refresh_sec=float(replays.get("refresh_sec", 60)),
        replays_paths=[str(p) for p in replays.get("paths", [])],
        replays_ks2_only=bool(replays.get("ks2_only", True)),
        replays_map_prefixes=tuple(
            str(prefix)
            for prefix in replays.get(
                "map_prefixes",
                ["凯瑞甘生存2", "Kerrigan Survival"],
            )
        ),
        replays_filename_priorities=tuple(
            str(item)
            for item in replays.get(
                "filename_priorities",
                ["凯瑞甘生存2 最新版"],
            )
        ),
        replay_upload_enabled=bool(replay_upload.get("enabled", True)),
        replay_upload_url=str(
            replay_upload.get("upload_url", "https://replay.kerrigansurvival.com/upload")
        ),
        replay_upload_user_agent=str(
            replay_upload.get("user_agent", "kerrigan-survival-uploader/1.07")
        ),
        replay_upload_max_bytes=int(
            replay_upload.get("max_file_bytes", 3 * 1024 * 1024)
        ),
        replay_upload_min_age_sec=float(replay_upload.get("min_age_sec", 5.0)),
        replay_upload_grace_sec=float(replay_upload.get("grace_period_sec", 120.0)),
        replay_upload_timeout_sec=float(replay_upload.get("timeout_sec", 60.0)),
        replay_upload_ks2_only=bool(replay_upload.get("ks2_only", True)),
        replay_upload_window_hours=float(replay_upload.get("window_hours", 48.0)),
        replay_upload_check_interval_sec=float(
            replay_upload.get("check_interval_sec", 300.0)
        ),
        replay_upload_grace_check_interval_sec=float(
            replay_upload.get("grace_check_interval_sec", 5.0)
        ),
        replay_upload_filename_markers=tuple(
            str(item)
            for item in replay_upload.get(
                "filename_markers",
                ["凯瑞甘生存2", "凯瑞甘生存", "Kerrigan Survival"],
            )
        ),
        replay_upload_use_filename_filter=bool(
            replay_upload.get("use_filename_filter", True)
        ),
        roster_enabled=bool(roster.get("enabled", False)),
        roster_sync_interval_sec=float(roster.get("sync_interval_sec", 300)),
        roster_sync_provider=str(roster_sync.get("provider", "disabled")),
        roster_sync_path=str(roster_sync.get("path", "config/player_roster.xlsx")),
        roster_sync_url=str(roster_sync.get("url", "")),
        roster_sync_push_enabled=bool(roster_sync.get("push_enabled", True)),
        roster_sync_push_from_replays=bool(
            roster_sync.get("push_from_replays", True)
        ),
        roster_former_name_prefix=str(
            roster_sync.get("former_name_prefix", "曾用名")
        ),
        roster_sync_fetch_url=str(roster_sync.get("fetch_url", "")),
        roster_sync_push_url=str(roster_sync.get("push_url", "")),
        roster_sync_api_key=str(roster_sync.get("api_key", "")),
        rules_pack_path=str(data_sources.get("rules_pack_path", "")),
        data_sources_confirmed=bool(data_sources.get("confirmed", False)),
    )


def apply_memory_runtime_defaults(config: AppConfig) -> AppConfig:
    """Force Mode 6 roster settings when the memory build is active."""
    from antismurf.build_meta import AUTO_KICK_ENABLED
    from antismurf.features import memory_scan_available

    if not memory_scan_available():
        return config
    if not AUTO_KICK_ENABLED:
        # Gray builds block automatic kicks only; manual kick / OCR testing may disable dry_run.
        config.auto_kick_enabled = False
    config.memory_enabled = True
    config.memory_scan_mode = "roster"
    config.memory_list_only = True
    config.memory_auto_enter_lobby = True
    config.memory_full_scan_fallback = False
    config.vision_enabled = False
    config.poll_interval_sec = min(config.poll_interval_sec, 2.0)
    config.poll_interval_in_room_sec = min(config.poll_interval_in_room_sec, 0.5)
    config.memory_scan_interval_sec = min(config.memory_scan_interval_sec, 2.0)
    config.memory_scan_interval_in_room_sec = min(
        config.memory_scan_interval_in_room_sec, 0.5
    )
    config.kick_fast_path = True
    if config.community_provider.strip().lower() in {"disabled", "off", "none", ""}:
        config.community_provider = "ks2wiki"
        if not config.community_base_url.strip():
            config.community_base_url = "https://wiki.ks2.top"
    from antismurf.config.kick_defaults import default_slot_regions, pad_slot_regions

    if not config.slot_regions:
        config.slot_regions = default_slot_regions()
    else:
        config.slot_regions = pad_slot_regions(config.slot_regions)
    labels = list(config.kick_menu_labels)
    for required in ("移出房间", "移除玩家", "Kick Player", "踢出玩家"):
        if required not in labels:
            labels.insert(0, required)
    config.kick_menu_labels = labels
    return config


def _load_blocklist_file(path: Path) -> set[str]:
    if not path.exists():
        return set()
    handles: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            handles.add(line)
    return handles


def _load_expression_rules(scoring: dict, data: dict) -> list[ExpressionRule]:
    from antismurf.config.expression_rules_io import expression_rules_from_raw_list
    from antismurf.scoring.presets import load_preset_rules

    raw_rules = scoring.get("expression_rules")
    if raw_rules:
        pass
    else:
        preset = str(scoring.get("preset", "balanced"))
        raw_rules = load_preset_rules(preset)

    if not raw_rules:
        raw_rules = load_preset_rules("balanced")

    return expression_rules_from_raw_list(raw_rules)


def _load_handle_mark_rules(scoring: dict) -> list[HandleMarkRule]:
    raw = scoring.get("handle_mark_rules")
    if not raw:
        return []
    marks: list[HandleMarkRule] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        handle = str(item.get("handle", "")).strip()
        if not handle:
            continue
        marks.append(
            HandleMarkRule(
                handle=handle,
                weight=float(item.get("weight", 100)),
                label=str(item.get("label", "")),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return marks


def _load_handle_trust_rules(scoring: dict) -> list[HandleTrustRule]:
    raw = scoring.get("handle_trust_rules")
    if not raw:
        return []
    rules: list[HandleTrustRule] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        handle = str(item.get("handle", "")).strip()
        if not handle:
            continue
        rules.append(
            HandleTrustRule(
                handle=handle,
                weight=float(item.get("weight", -20)),
                label=str(item.get("label", "")),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return rules


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def user_config_path() -> Path:
    return _project_root() / "config" / "user.toml"


def _format_region(region: dict[str, float]) -> str:
    return (
        f'{{ x = {region["x"]}, y = {region["y"]}, '
        f'w = {region.get("w", 0.02)}, h = {region.get("h", 0.02)} }}'
    )


def save_user_calibration(config: AppConfig) -> Path:
    """Persist user overrides to user.toml."""
    return save_user_config(config)


def save_user_config(config: AppConfig) -> Path:
    from antismurf.config.expression_rules_io import format_toml_value

    path = user_config_path()
    lines = [
        "# AntiSmurf user configuration",
        "",
        "[host]",
        f'handle = "{config.host_handle}"',
        "",
        "[scoring]",
        f"kick_threshold = {config.kick_threshold}",
        f"tier_medium = {config.tier_medium}",
        f"tier_high = {config.tier_high}",
        f"tier_critical = {config.tier_critical}",
        f'preset = "{config.scoring_preset}"',
        "",
    ]
    for rule in config.expression_rules:
        lines.append("[[scoring.expression_rules]]")
        lines.append(f'id = "{rule.id}"')
        lines.append(f"enabled = {'true' if rule.enabled else 'false'}")
        lines.append(f'label = "{rule.label}"')
        lines.append(f'left = "{rule.left}"')
        if rule.arith_op:
            lines.append(f'arith_op = "{rule.arith_op}"')
        if rule.middle:
            lines.append(f'middle = "{rule.middle}"')
        lines.append(f'op = "{rule.op}"')
        lines.append(f"right = {format_toml_value(rule.right)}")
        if rule.right2 not in ("", None):
            lines.append(f"right2 = {format_toml_value(rule.right2)}")
        lines.append(f"weight = {rule.weight}")
        lines.append(f"else_weight = {rule.else_weight}")
        if rule.min_games:
            lines.append(f"min_games = {rule.min_games}")
        lines.append("")

    for mark in config.handle_mark_rules:
        lines.append("[[scoring.handle_mark_rules]]")
        lines.append(f'handle = "{mark.handle}"')
        lines.append(f"weight = {mark.weight}")
        if mark.label:
            lines.append(f'label = "{mark.label}"')
        lines.append(f"enabled = {'true' if mark.enabled else 'false'}")
        lines.append("")

    for trust in config.handle_trust_rules:
        lines.append("[[scoring.handle_trust_rules]]")
        lines.append(f'handle = "{trust.handle}"')
        lines.append(f"weight = {trust.weight}")
        if trust.label:
            lines.append(f'label = "{trust.label}"')
        lines.append(f"enabled = {'true' if trust.enabled else 'false'}")
        lines.append("")

    lines.extend([
        "[actions]",
        f"dry_run = {'true' if config.dry_run else 'false'}",
        f"auto_kick_enabled = {'true' if config.auto_kick_enabled else 'false'}",
        f"whitelist_mode = {'true' if config.whitelist_mode else 'false'}",
        f"kick_menu_down_presses = {config.kick_menu_down_presses}",
        f"kick_fast_path = {'true' if config.kick_fast_path else 'false'}",
        f"kick_ocr_fallback = {'true' if config.kick_ocr_fallback else 'false'}",
        f"kick_menu_open_wait_sec = {config.kick_menu_open_wait_sec}",
        f"kick_focus_wait_sec = {config.kick_focus_wait_sec}",
        f"kick_save_debug_shots = {'true' if config.kick_save_debug_shots else 'false'}",
        f"profile_menu_down_presses = {config.profile_menu_down_presses}",
        "",
        "[community]",
        f'provider = "{config.community_provider}"',
        f'base_url = "{config.community_base_url}"',
        f'api_key = "{config.community_api_key}"',
        "",
        "[ui]",
        f'window_title_contains = "{config.window_title_contains}"',
        f"notify_high_suspicion = {'true' if config.notify_high_suspicion else 'false'}",
        "",
        "[ai]",
        f'api_base_url = "{config.ai_api_base_url}"',
        f'api_key = "{config.ai_api_key}"',
        f'model = "{config.ai_model}"',
        "",
        "[calibration]",
    ])
    if config.map_region:
        lines.append("[calibration.map_region]")
        lines.append(f"x = {config.map_region.get('x', 0.35)}")
        lines.append(f"y = {config.map_region.get('y', 0.02)}")
        lines.append(f"w = {config.map_region.get('w', 0.30)}")
        lines.append(f"h = {config.map_region.get('h', 0.05)}")
        lines.append("")
    if config.kick_menu_remove_region:
        lines.append("[calibration.kick_menu_remove_region]")
        lines.append(f"x = {config.kick_menu_remove_region.get('x', 0)}")
        lines.append(f"y = {config.kick_menu_remove_region.get('y', 0)}")
        lines.append("")
    if config.kick_menu_offset:
        lines.append("[calibration.kick_menu_offset]")
        lines.append(f"dx = {config.kick_menu_offset.get('dx', 0)}")
        lines.append(f"dy = {config.kick_menu_offset.get('dy', 0)}")
        lines.append("")
    if config.kick_slot_step:
        lines.append("[calibration.kick_slot_step]")
        lines.append(f"dx = {config.kick_slot_step.get('dx', 0)}")
        lines.append(f"dy = {config.kick_slot_step.get('dy', 0)}")
        lines.append("")
    for slot in config.slot_id_regions:
        lines.append("[[calibration.slot_id_regions]]")
        lines.append(f"x = {slot['x']}")
        lines.append(f"y = {slot['y']}")
        if "w" in slot:
            lines.append(f"w = {slot['w']}")
        if "h" in slot:
            lines.append(f"h = {slot['h']}")
        lines.append("")
    lines.append("")
    for slot in config.slot_regions:
        lines.append("[[calibration.slot_regions]]")
        lines.append(f"x = {slot['x']}")
        lines.append(f"y = {slot['y']}")
        if "w" in slot:
            lines.append(f"w = {slot['w']}")
        if "h" in slot:
            lines.append(f"h = {slot['h']}")
        lines.append("")

    lines.extend([
        "[vision]",
        f"enabled = {'true' if config.vision_enabled else 'false'}",
        f"scan_interval_sec = {config.vision_scan_interval_sec}",
        "",
        "[memory]",
        f"enabled = {'true' if config.memory_enabled else 'false'}",
        f"chunk_size = {config.memory_chunk_size}",
        f"handle_scan_budget_sec = {config.memory_handle_scan_budget_sec}",
        f"name_search_radius = {config.memory_name_search_radius}",
        f"scan_interval_sec = {config.memory_scan_interval_sec}",
        f"scan_interval_in_room_sec = {config.memory_scan_interval_in_room_sec}",
        f"record_enabled = {'true' if config.memory_record_enabled else 'false'}",
        f"targeted_scan_enabled = {'true' if config.memory_targeted_scan_enabled else 'false'}",
        f"targeted_region_limit = {config.memory_targeted_region_limit}",
        f"targeted_min_regions = {config.memory_targeted_min_regions}",
        f"targeted_min_handles = {config.memory_targeted_min_handles}",
        f"full_scan_fallback = {'true' if config.memory_full_scan_fallback else 'false'}",
        f"host_handle_module_offset = \"0x{config.memory_host_handle_module_offset:X}\"",
        f"host_anchor_scan_radius = {config.memory_host_anchor_scan_radius}",
        f"host_anchor_enabled = {'true' if config.memory_host_anchor_enabled else 'false'}",
        f"host_anchor_sniff_enabled = {'true' if config.memory_host_anchor_sniff_enabled else 'false'}",
        f"handle_reconfirm_threshold_sec = {config.memory_handle_reconfirm_threshold_sec}",
        f"scan_mode = \"{config.memory_scan_mode}\"",
        f"calibration_path = \"{config.memory_calibration_path}\"",
        f"roster_rescan_budget_sec = {config.memory_roster_rescan_budget_sec}",
        f"roster_rescan_every_scans = {config.memory_roster_rescan_every_scans}",
        f"roster_rescan_every_scans_in_room = {config.memory_roster_rescan_every_scans_in_room}",
        f"target_pid = {config.memory_target_pid}",
        f"list_only = {'true' if config.memory_list_only else 'false'}",
        f"auto_enter_lobby = {'true' if config.memory_auto_enter_lobby else 'false'}",
        "",
        "[replays]",
        f"enabled = {'true' if config.replays_enabled else 'false'}",
        f"max_count = {config.replays_max_count}",
        f"refresh_sec = {config.replays_refresh_sec}",
    ])
    if config.replays_paths:
        paths_inline = ", ".join(f'"{p}"' for p in config.replays_paths)
        lines.append(f"paths = [{paths_inline}]")
    else:
        lines.append("paths = []")
    lines.extend([
        "",
        "[roster]",
        f"enabled = {'true' if config.roster_enabled else 'false'}",
        f"sync_interval_sec = {config.roster_sync_interval_sec}",
        "",
        "[roster.sync]",
        f'provider = "{config.roster_sync_provider}"',
        f'path = "{config.roster_sync_path}"',
        f'url = "{config.roster_sync_url}"',
        f'fetch_url = "{config.roster_sync_fetch_url}"',
        f'push_url = "{config.roster_sync_push_url}"',
        f'api_key = "{config.roster_sync_api_key}"',
        f"push_enabled = {'true' if config.roster_sync_push_enabled else 'false'}",
        f"push_from_replays = {'true' if config.roster_sync_push_from_replays else 'false'}",
        f'former_name_prefix = "{config.roster_former_name_prefix}"',
        "",
        "[data_sources]",
        f'rules_pack_path = "{config.rules_pack_path}"',
        f"confirmed = {'true' if config.data_sources_confirmed else 'false'}",
        "",
    ])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
