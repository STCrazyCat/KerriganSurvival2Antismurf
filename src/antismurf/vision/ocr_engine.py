from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Protocol

if True:
    from PIL import Image

logger = logging.getLogger(__name__)

_paddle_lock = threading.Lock()
_paddle_instance = None


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float


class OcrEngine(Protocol):
    def recognize(self, image: Image.Image) -> list[OcrLine]:
        ...


class PaddleOcrEngine:
    """Lazy-loaded PaddleOCR wrapper (singleton per process)."""

    def __init__(self, *, use_gpu: bool = False, min_confidence: float = 0.5) -> None:
        self._use_gpu = use_gpu
        self._min_confidence = min_confidence
        self._ocr = None

    def _ensure_loaded(self) -> None:
        global _paddle_instance
        if _paddle_instance is not None:
            self._ocr = _paddle_instance
            return
        with _paddle_lock:
            if _paddle_instance is not None:
                self._ocr = _paddle_instance
                return
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise RuntimeError(
                    "PaddleOCR is not installed. Run: pip install paddleocr paddlepaddle"
                ) from exc
            logger.info("Loading PaddleOCR model (first run may download weights)...")
            _paddle_instance = PaddleOCR(
                use_angle_cls=False,
                lang="ch",
                use_gpu=self._use_gpu,
                show_log=False,
            )
            self._ocr = _paddle_instance

    def recognize(self, image: Image.Image) -> list[OcrLine]:
        self._ensure_loaded()
        import numpy as np

        array = np.array(image.convert("RGB"))
        raw = self._ocr.ocr(array, cls=False)
        lines: list[OcrLine] = []
        if not raw:
            return lines
        for block in raw:
            if not block:
                continue
            for item in block:
                if not item or len(item) < 2:
                    continue
                text_info = item[1]
                if not text_info or len(text_info) < 2:
                    continue
                text = str(text_info[0]).strip()
                confidence = float(text_info[1])
                if not text or confidence < self._min_confidence:
                    continue
                lines.append(OcrLine(text=text, confidence=confidence))
        return lines


def create_ocr_engine(
    engine: str,
    *,
    use_gpu: bool = False,
    min_confidence: float = 0.5,
) -> OcrEngine:
    name = (engine or "paddleocr").lower()
    if name == "paddleocr":
        return PaddleOcrEngine(use_gpu=use_gpu, min_confidence=min_confidence)
    raise ValueError(f"Unsupported OCR engine: {engine}")
