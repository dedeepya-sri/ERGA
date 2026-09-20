"""
Image preprocessing for OCR (handwriting/scanned-photo cleanup).

Designed to slot into TesseractOCREngine.recognize(), which already
receives a loaded image as a numpy.ndarray. This module takes that same
array in, and returns a cleaned-up array ready for pytesseract — no file
I/O, no path handling.
"""
from __future__ import annotations

import cv2
import numpy as np


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """
    Clean up a photographed/scanned page image before OCR.

    Steps: grayscale -> upscale -> denoise -> adaptive threshold -> deskew.
    Each step targets a specific, common failure mode of phone photos of
    handwriting: low resolution, paper texture noise, uneven lighting, and
    slight rotation.
    """
    # 1. Ensure grayscale (Tesseract/most OCR preprocessing expects single-channel)
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # 2. Upscale — improves character detail for Tesseract's segmentation
    scale = 2.0
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # 3. Denoise — removes paper grain/texture that fragments strokes
    gray = cv2.fastNlMeansDenoising(gray, h=15)

    # 4. Adaptive threshold — clean black/white, robust to uneven lighting/shadows
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=15,
    )

    # 5. Deskew — corrects slight rotation from an off-angle photo
    coords = np.column_stack(np.where(binary < 255))
    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        angle = -(90 + angle) if angle < -45 else -angle
        if abs(angle) > 0.5:
            (h, w) = binary.shape
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            binary = cv2.warpAffine(
                binary, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )

    return binary