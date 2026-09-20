"""
Handwriting OCR via Microsoft TrOCR (services/ocr_trocr.py).

TrOCR is a line-level recognizer: one call = one line of text. So the page
image must be segmented into individual line crops first (see
`segment_lines`), then each line is run through the model separately and
the results are reassembled into an OCRPageResult, matching the same shape
TesseractOCREngine already produces.

Confidence is computed from the model's own token-level output
probabilities (mean of the max softmax probability at each generated
token) — a genuine per-line confidence, not a fabricated number, in
keeping with this codebase's existing rule against fabricating figures.

Line bounding boxes ARE real (derived from the actual row-projection split
points), but they are coarse — full-line boxes, not per-word boxes like
Tesseract provides, since TrOCR does not localize words. If per-word boxes
are ever needed downstream, that would require an added word-detection
step; this implementation does not fabricate word-level boxes to fill that
gap.

Model note: this downloads ~1.3GB of weights from Hugging Face Hub
(microsoft/trocr-base-handwritten) the first time it runs. Requires
outbound internet access to huggingface.co on whatever machine runs this.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from services.ocr import OCREngine, OCRLine, OCRPageResult
from services.ocr_preprocess import preprocess_image

_processor = None
_model = None


def _load_model():
    """Lazy-load so import of this module doesn't force a download at
    import time — only when a TrOCREngine is actually used."""
    global _processor, _model
    if _model is None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
        _processor = TrOCRProcessor.from_pretrained("microsoft/trocr-base-handwritten")
        _model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-base-handwritten")
        _model.eval()
    return _processor, _model


def segment_lines(binary_image: np.ndarray, min_line_height: int = 15, padding: int = 6) -> list[dict]:
    """
    Split a binarized page image into line crops using horizontal
    row-projection: rows with ink are 'in a line', rows with (near) no ink
    are gaps between lines.

    Returns a list of {"bbox": {left, top, width, height}} dicts, in the
    coordinate space of `binary_image`, ordered top-to-bottom.
    """
    h, w = binary_image.shape
    # Ink = dark pixels (adaptiveThreshold output: text is 0/black, background 255/white)
    ink_mask = (binary_image < 128).astype(np.uint8)
    row_ink_counts = ink_mask.sum(axis=1)

    threshold = max(1, int(0.002 * w))  # a row counts as "text" if it has at least this many ink pixels
    is_text_row = row_ink_counts > threshold

    lines = []
    in_line = False
    start = 0
    for y in range(h):
        if is_text_row[y] and not in_line:
            in_line = True
            start = y
        elif not is_text_row[y] and in_line:
            in_line = False
            end = y
            if end - start >= min_line_height:
                top = max(0, start - padding)
                bottom = min(h, end + padding)
                lines.append({
                    "bbox": {"left": 0, "top": top, "width": w, "height": bottom - top}
                })
    if in_line:
        end = h
        if end - start >= min_line_height:
            top = max(0, start - padding)
            bottom = min(h, end)
            lines.append({
                "bbox": {"left": 0, "top": top, "width": w, "height": bottom - top}
            })
    return lines


def _recognize_line(line_img: np.ndarray) -> tuple[str, float]:
    """Run TrOCR on a single line-crop image. Returns (text, confidence 0-1)."""
    processor, model = _load_model()

    # TrOCR expects RGB PIL input
    if len(line_img.shape) == 2:
        rgb = cv2.cvtColor(line_img, cv2.COLOR_GRAY2RGB)
    else:
        rgb = line_img
    pil_img = Image.fromarray(rgb)

    pixel_values = processor(images=pil_img, return_tensors="pt").pixel_values

    import torch
    with torch.no_grad():
        outputs = model.generate(
            pixel_values,
            output_scores=True,
            return_dict_in_generate=True,
        )

    generated_ids = outputs.sequences
    text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

    # Genuine confidence: mean of the max softmax probability at each
    # generated token step (not fabricated — derived directly from the
    # model's own output distribution).
    if outputs.scores:
        probs = [torch.softmax(step_logits[0], dim=-1).max().item() for step_logits in outputs.scores]
        confidence = sum(probs) / len(probs) if probs else 0.0
    else:
        confidence = 0.0

    return text, round(confidence, 4)


class TrOCREngine(OCREngine):
    name = "trocr"

    def recognize(self, image: np.ndarray, page: int, lang: str, psm: int) -> OCRPageResult:
        # lang/psm are unused by TrOCR (Tesseract-specific concepts) but
        # kept in the signature to satisfy the shared OCREngine interface.
        binary = preprocess_image(image)  # reuse existing grayscale/denoise/threshold/deskew
        line_boxes = segment_lines(binary)

        lines: list[OCRLine] = []
        all_confidences: list[float] = []

        for lb in line_boxes:
            b = lb["bbox"]
            crop = binary[b["top"]: b["top"] + b["height"], b["left"]: b["left"] + b["width"]]
            if crop.size == 0:
                continue
            text, conf = _recognize_line(crop)
            if not text:
                continue
            lines.append(OCRLine(text=text, confidence=conf, bbox=b))
            all_confidences.append(conf)

        mean_conf = (sum(all_confidences) / len(all_confidences)) if all_confidences else 0.0
        return OCRPageResult(page=page, lines=lines, mean_confidence=round(mean_conf, 4))