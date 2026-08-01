#!/usr/bin/env python3
"""Scan local SC2 replays and show handle/display-name bindings."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import load_config
from antismurf.replay.local_replays import (
    LocalReplayIndex,
    discover_recent_replay_candidates,
    find_replay_roots_for_handle,
    ingest_replay_path,
    parse_replay_bundle,
    resolve_replay_search_paths,
)
from antismurf.replay.replay_binding_store import ReplayBindingStore


def _print_bindings(bindings: list[dict]) -> None:
    if not bindings:
        print("  (无玩家绑定)")
        return
    for item in bindings:
        handle = item.get("handle") or "-"
        name = item.get("display_name") or "-"
        pid = item.get("profile_id")
        pid_text = f" profile_id={pid}" if pid is not None else ""
        print(f"  {handle}  <=>  {name}{pid_text}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="扫描本地星际争霸2录像，建立句柄与玩家名绑定数据库",
    )
    parser.add_argument(
        "--file",
        help="扫描单个 .SC2Replay 文件",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="扫描目录（可多次指定）；默认使用配置与本机句柄自动发现",
    )
    parser.add_argument(
        "--handle",
        help="本机句柄，用于定位 Documents/StarCraft II/Accounts/.../Replays/Multiplayer",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="目录扫描时最多处理的录像数量",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="忽略已扫描缓存，强制重新解析",
    )
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="仅解析并打印，不写入 data/replay_bindings.db",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 输出结果",
    )
    args = parser.parse_args()

    config = load_config()
    host_handle = (args.handle or config.host_handle or "").strip() or None

    if args.file:
        file_path = Path(args.file)
        if args.preview_only:
            bundle = parse_replay_bundle(file_path, config)
            result = {
                "path": str(file_path),
                "map_name": bundle.map_name,
                "is_ks2": bundle.is_ks2,
                "bindings": [
                    {
                        "handle": b.handle,
                        "display_name": b.display_name,
                        "profile_id": b.profile_id,
                    }
                    for b in bundle.bindings
                ],
            }
        else:
            store = ReplayBindingStore()
            result = ingest_replay_path(
                file_path,
                config,
                store,
                force=args.force,
            )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"文件: {result['path']}")
            print(f"地图: {result.get('map_name') or '-'}")
            print(f"KS2: {result.get('is_ks2')}")
            if result.get("skipped"):
                print("状态: 已缓存，跳过解析（使用 --force 强制）")
            _print_bindings(result.get("bindings", []))
        return 0

    if args.path:
        search_paths = args.path
    else:
        search_paths = resolve_replay_search_paths(config.replays_paths, host_handle)

    if args.json:
        output: dict = {"search_paths": search_paths, "files": []}
    else:
        print("扫描目录:")
        for item in search_paths:
            print(f"  {item}")
        if host_handle:
            roots = find_replay_roots_for_handle(host_handle)
            if roots:
                print("句柄对应录像目录:")
                for root in roots:
                    print(f"  {root}")

    if not search_paths:
        print("未找到可扫描的录像目录。请配置 [host].handle 或 replays.paths。", file=sys.stderr)
        return 1

    candidates = discover_recent_replay_candidates(
        search_paths,
        candidate_limit=max(args.limit * 5, args.limit),
        filename_priorities=config.replays_filename_priorities,
    )[: args.limit]

    if args.preview_only:
        for path in candidates:
            bundle = parse_replay_bundle(path, config)
            entry = {
                "path": str(path),
                "map_name": bundle.map_name,
                "is_ks2": bundle.is_ks2,
                "bindings": [
                    {
                        "handle": b.handle,
                        "display_name": b.display_name,
                        "profile_id": b.profile_id,
                    }
                    for b in bundle.bindings
                ],
            }
            if args.json:
                output["files"].append(entry)
            else:
                print(f"\n{path.name}")
                print(f"  地图: {bundle.map_name or '-'} | KS2: {bundle.is_ks2}")
                _print_bindings(entry["bindings"])
        if args.json:
            print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    index = LocalReplayIndex(config)
    if host_handle:
        index.set_local_handle(host_handle)
    scanned = 0
    bindings_total = 0
    file_results: list[dict] = []
    for path in candidates:
        result = index.scan_file(path, force=args.force)
        if result.get("skipped"):
            continue
        scanned += 1
        bindings_total += len(result.get("bindings", []))
        file_results.append(result)

    preview = index.preview()
    if args.json:
        print(
            json.dumps(
                {
                    "search_paths": search_paths,
                    "parsed_files": scanned,
                    "bindings_written": bindings_total,
                    "files": file_results,
                    "store": preview.get("store"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"\n已解析 {scanned} 个新/变更录像，写入 {bindings_total} 条玩家绑定")
        print(
            f"数据库: data/replay_bindings.db | "
            f"累计句柄: {preview.get('store', {}).get('binding_count', '?')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
