"""
OCR / handwriting recognition (Section 7).

  * TesseractOCREngine — the only OCR engine active in this build. Works
    genuinely for printed/typed-and-scanned text, with real per-word
    confidence and bounding boxes aggregated into lines (never fabricated —
    Section 25: "If exact region mapping isn't available, don't fabricate
    coordinates"; Tesseract actually provides them, so we use the real
    ones).

  * Handwriting: there is no honest way to do real handwritten-text
    recognition without a pretrained HTR model (e.g. Microsoft TrOCR, or
    PaddleOCR's handwriting mode) — both require downloading weights from a
    model hub this sandbox cannot reach. Rather than claim Tesseract (built
    for printed text) reliably reads cursive, handwritten submissions are
    still run through this same pipeline as a best-effort fallback, AND the
    API layer unconditionally routes them to faculty review regardless of
    the confidence number reported (Section 36: "Don't pretend OCR is
    perfect"). See PaddleOCREngine below for the real extension point.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import numpy as np
import pytesseract
from pytesseract import Output

from config.settings import Config


@dataclass
class OCRWord:
    text: str
    confidence: float  # 0-100, as Tesseract reports it
    left: int
    top: int
    width: int
    height: int


@dataclass
class OCRLine:
    text: str
    confidence: float  # 0-1, mean of this line's word confidences
    bbox: dict = field(default_factory=dict)  # {left, top, width, height}, union of word boxes


@dataclass
class OCRPageResult:
    page: int
    lines: list[OCRLine]
    mean_confidence: float  # 0-1, mean of all word confidences on the page


def _union_bbox(words: list[OCRWord]) -> dict:
    lefts = [w.left for w in words]
    tops = [w.top for w in words]
    rights = [w.left + w.width for w in words]
    bottoms = [w.top + w.height for w in words]
    return {
        "left": min(lefts),
        "top": min(tops),
        "width": max(rights) - min(lefts),
        "height": max(bottoms) - min(tops),
    }


class OCREngine(ABC):
    name: str

    @abstractmethod
    def recognize(self, image: np.ndarray, page: int, lang: str, psm: int) -> OCRPageResult:
        """Run OCR on a single preprocessed page image."""


class TesseractOCREngine(OCREngine):
    name = "tesseract"

    def recognize(self, image: np.ndarray, page: int, lang: str, psm: int) -> OCRPageResult:
        config_str = f"--psm {psm}"
        data = pytesseract.image_to_data(
            image, lang=lang, config=config_str, output_type=Output.DICT
        )

        line_groups: dict[tuple[int, int, int], list[OCRWord]] = {}
        all_confidences: list[float] = []

        n = len(data["text"])
        for i in range(n):
            text = data["text"][i].strip()
            conf = float(data["conf"][i])
            if not text or conf < 0:
                continue
            word = OCRWord(
                text=text,
                confidence=conf,
                left=int(data["left"][i]),
                top=int(data["top"][i]),
                width=int(data["width"][i]),
                height=int(data["height"][i]),
            )
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            line_groups.setdefault(key, []).append(word)
            all_confidences.append(conf)

        lines: list[OCRLine] = []
        for key in sorted(line_groups.keys()):
            words = line_groups[key]
            text = " ".join(w.text for w in words)
            mean_conf = sum(w.confidence for w in words) / len(words) / 100.0
            lines.append(OCRLine(text=text, confidence=round(mean_conf, 4), bbox=_union_bbox(words)))

        mean_conf_page = (sum(all_confidences) / len(all_confidences) / 100.0) if all_confidences else 0.0
        return OCRPageResult(page=page, lines=lines, mean_confidence=round(mean_conf_page, 4))


class PaddleOCREngine(OCREngine):
    """
    Extension point for PaddleOCR (Section 38 names it as an alternative
    starting point). Not implemented here: paddleocr downloads its
    detection/recognition models from Baidu/Paddle model servers, which
    this sandbox's egress allowlist does not include, so a working
    implementation cannot be verified in this build. To enable it: install
    `paddleocr`/`paddlepaddle`, implement `recognize()` below against their
    `PaddleOCR(...).ocr(image)` API, and set ocr.engine: paddleocr in
    model_config.yaml in an environment with model access.
    """

    name = "paddleocr"

    def recognize(self, image: np.ndarray, page: int, lang: str, psm: int) -> OCRPageResult:
        raise NotImplementedError(
            "PaddleOCR support is not implemented in this build (see the "
            "class docstring in services/ocr.py). Use ocr.engine: tesseract."
        )


def get_ocr_engine(config: Config) -> OCREngine:
    if config.ocr.engine == "paddleocr":
        return PaddleOCREngine()
    return TesseractOCREngine()
