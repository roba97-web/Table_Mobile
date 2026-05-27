"""정원표 분석 결과 PDF (reportlab + TTF, Android 뷰어 호환)."""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table, TableStyle

from pdf_font import korean_font_path

FINAL_COLUMNS = ["구분", "총정원", "정무직", "고공단", "3·4급", "4급", "4.5급", "5급이하"]
RANK_COLS = ["정무직", "고공단", "3·4급", "4급", "4.5급", "5급이하"]
SUM_COLS = ["총정원", *RANK_COLS]
PDF_FILE_NAME = "통합_정원표_분석결과.pdf"

_FONT_NAME = "KoreanPDF"
_FONT_REGISTERED = False


def _register_font() -> None:
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    font_path = korean_font_path()
    pdfmetrics.registerFont(TTFont(_FONT_NAME, font_path))
    _FONT_REGISTERED = True


def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _format_number(value) -> str:
    n = _to_int(value)
    if n == 0:
        return "0"
    return f"{n:,}"


def _format_share_text(count: int, total: int) -> str:
    if count == 0:
        return "-"
    if total <= 0:
        return _format_number(count)
    pct = count / total * 100
    return f"{_format_number(count)}<br/>({pct:.1f})"


def _cell_text(col: str, row: dict) -> str:
    total = _to_int(row.get("총정원", 0))
    if col in RANK_COLS:
        return _format_share_text(_to_int(row.get(col)), total)
    if col in SUM_COLS:
        return _format_number(row.get(col))
    return str(row.get(col, ""))


def _para(text: str, *, bold: bool = False, size: int = 8) -> Paragraph:
    style = ParagraphStyle(
        name="Cell",
        fontName=_FONT_NAME,
        fontSize=size,
        leading=size + 2,
        alignment=1,
        wordWrap="CJK",
    )
    if bold:
        style = ParagraphStyle(
            name="Head",
            parent=style,
            fontSize=size,
            leading=size + 2,
        )
    raw = str(text).replace("&", "&amp;")
    if "<br/>" in raw:
        parts = raw.split("<br/>")
        safe = "<br/>".join(p.replace("<", "&lt;").replace(">", "&gt;") for p in parts)
    else:
        safe = raw.replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(safe, style)


def build_result_pdf_bytes(columns: list[str], rows: list[dict]) -> bytes:
    if not columns:
        raise ValueError("표 열이 없습니다.")

    _register_font()

    buf = io.BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=10 * mm,
    )

    title_style = ParagraphStyle(
        name="Title",
        fontName=_FONT_NAME,
        fontSize=14,
        leading=18,
        alignment=1,
        spaceAfter=6,
    )
    story = [Paragraph("통합 정원표 분석결과", title_style)]

    weights = [2.0 if col == "구분" else 1.0 for col in columns]
    wsum = sum(weights)
    usable = page_size[0] - doc.leftMargin - doc.rightMargin
    col_widths = [usable * w / wsum for w in weights]

    table_data: list[list[Paragraph]] = [[_para(str(c), bold=True, size=9) for c in columns]]
    for row in rows:
        table_data.append([_para(_cell_text(col, row), size=8) for col in columns])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, -1), _FONT_NAME, 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f4f6")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)
    doc.build(story)

    data = buf.getvalue()
    if not data.startswith(b"%PDF"):
        raise ValueError("PDF 생성에 실패했습니다.")
    return data
