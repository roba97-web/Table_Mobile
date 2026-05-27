"""한글 PDF용 폰트 경로 (Windows·Linux·프로젝트 내 fonts/)."""

from __future__ import annotations

import os
from pathlib import Path

_FONT_DIR = Path(__file__).resolve().parent / "fonts"

# Windows → Linux(Cloud) → 프로젝트 fonts/ 순
_FONT_CANDIDATES: tuple[str, ...] = (
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\gulim.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansKR-Regular.otf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    str(_FONT_DIR / "NotoSansKR-Regular.otf"),
    str(_FONT_DIR / "NotoSansKR-Regular.ttf"),
    str(_FONT_DIR / "malgun.ttf"),
)

_FONT_ERROR = (
    "한글 PDF 폰트를 찾을 수 없습니다. "
    "로컬(Windows): 맑은 고딕 설치 · "
    "배포(Streamlit Cloud): 저장소 루트에 packages.txt( fonts-noto-cjk ) 필요"
)


def korean_font_path() -> str:
    for path in _FONT_CANDIDATES:
        if os.path.isfile(path):
            return path
    raise OSError(_FONT_ERROR)
