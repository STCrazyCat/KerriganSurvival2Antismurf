from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def notify(title: str, message: str) -> bool:
    try:
        from winotify import Notification, audio

        toast = Notification(
            app_id="AntiSmurf",
            title=title,
            msg=message,
            duration="short",
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        return True
    except Exception as exc:
        logger.debug("winotify failed: %s", exc)

    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0, message, title, 0x40
        )
        return True
    except Exception:
        return False
