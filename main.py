#!/usr/bin/env python3
"""AntiSmurf — Kerrigan Survival 2 anti-smurf lobby tool."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    from antismurf.build_meta import APP_DISPLAY_NAME, BUILD_VERSION, MEMORY_SCAN_AVAILABLE
    from antismurf.config.settings import apply_memory_runtime_defaults, load_config

    parser = argparse.ArgumentParser(description="AntiSmurf KS2 lobby tool")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run orchestrator without GUI",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = apply_memory_runtime_defaults(load_config())
    flavor = "memory-mode6" if MEMORY_SCAN_AVAILABLE else "vision"
    logging.getLogger(__name__).info(
        "Starting %s build %s (%s)",
        APP_DISPLAY_NAME,
        BUILD_VERSION,
        flavor,
    )

    if args.headless:
        import asyncio

        from antismurf.app.orchestrator import Orchestrator

        async def run() -> None:
            orch = Orchestrator(config)
            await orch.start()
            try:
                while True:
                    await asyncio.sleep(3600)
            except KeyboardInterrupt:
                await orch.stop()

        asyncio.run(run())
    else:
        from antismurf.app.gui import run_gui

        run_gui(config)


if __name__ == "__main__":
    main()
