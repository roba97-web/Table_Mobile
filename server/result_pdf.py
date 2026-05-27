"""정원표 분석 결과 PDF (한글 폰트·비중·천단위 콤마)."""

from __future__ import annotations

from fpdf import FPDF

from pdf_font import korean_font_path

FINAL_COLUMNS = ["구분", "총정원", "정무직", "고공단", "3·4급", "4급", "4.5급", "5급이하"]
RANK_COLS = ["정무직", "고공단", "3·4급", "4급", "4.5급", "5급이하"]
SUM_COLS = ["총정원", *RANK_COLS]
PDF_FILE_NAME = "통합_정원표_분석결과.pdf"


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
    return f"{_format_number(count)} ({pct:.1f})"


def _cell_text(col: str, row: dict) -> str:
    total = _to_int(row.get("총정원", 0))
    if col in RANK_COLS:
        return _format_share_text(_to_int(row.get(col)), total)
    if col in SUM_COLS:
        return _format_number(row.get(col))
    return str(row.get(col, ""))


def build_result_pdf_bytes(columns: list[str], rows: list[dict]) -> bytes:
    font_path = korean_font_path()

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_margins(10, 10, 10)
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    pdf.add_font("Korean", "", font_path)
    pdf.set_font("Korean", size=11)
    pdf.cell(0, 8, "통합 정원표 분석결과", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)
    pdf.set_font("Korean", size=8)

    n = len(columns)
    if n == 0:
        raise ValueError("표 열이 없습니다.")

    usable = pdf.epw
    weights = [2.0 if col == "구분" else 1.0 for col in columns]
    wsum = sum(weights)
    col_widths = [usable * w / wsum for w in weights]
    line_h = 7.0

    def draw_row(cells: list[str]) -> None:
        x0 = pdf.l_margin
        y0 = pdf.get_y()
        if y0 > 270:
            pdf.add_page()
            pdf.set_font("Korean", size=8)
            y0 = pdf.get_y()

        row_h = line_h
        for i, text in enumerate(cells):
            x = x0 + sum(col_widths[:i])
            pdf.set_xy(x, y0)
            pdf.multi_cell(col_widths[i], line_h, text, border=0, align="C")
            row_h = max(row_h, pdf.get_y() - y0)
            pdf.set_xy(x, y0)

        for i in range(n):
            x = x0 + sum(col_widths[:i])
            pdf.rect(x, y0, col_widths[i], row_h)
        pdf.set_y(y0 + row_h)

    draw_row([str(c) for c in columns])
    for row in rows:
        draw_row([_cell_text(col, row) for col in columns])

    out = pdf.output()
    data = bytes(out) if isinstance(out, (bytes, bytearray)) else out.encode("latin-1")
    if not data.startswith(b"%PDF"):
        raise ValueError("PDF 생성에 실패했습니다.")
    return data
