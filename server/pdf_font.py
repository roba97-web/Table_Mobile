"""한글 PDF용 폰트 경로 (TTF 우선, Android PDF 뷰어 호환)."""

from __future__ import annotations

import os
from pathlib import Path

_FONT_DIR = Path(__file__).resolve().parent / "fonts"

# TTF만 사용 — fpdf2/OTF/Type0(CID)는 Android 기본 PDF 뷰어에서 깨짐
_FONT_CANDIDATES: tuple[str, ...] = (
    str(_FONT_DIR / "NanumGothic-Regular.ttf"),
    str(_FONT_DIR / "NotoSansKR-Regular.ttf"),
    str(_FONT_DIR / "malgun.ttf"),
    r"C:\Windows\Fonts\malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicRegular.ttf",
)

_FONT_ERROR = (
    "한글 PDF 폰트(TTF)를 찾을 수 없습니다. "
    "server/fonts/NanumGothic-Regular.ttf 가 포함되어 있는지 확인하세요."
)


def korean_font_path() -> str:
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    raise OSError(_FONT_ERROR)
