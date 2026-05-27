"""정원표 PDF 텍스트 분석."""

from __future__ import annotations

import io
import re

import PyPDF2


def analyze_staff_table_pdf(org_name: str, pdf_bytes: bytes) -> dict[str, int | str]:
    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
    text = ""
    for page in reader.pages:
        if page.extract_text():
            text += page.extract_text() + "\n"

    lines = text.split("\n")
    merged_lines: list[str] = []
    current_line = ""
    for line in lines:
        cleaned = line.replace(" ", "").strip()
        current_line += cleaned
        if re.search(r"\d+$", current_line):
            merged_lines.append(current_line)
            current_line = ""

    total = 0
    count_jungmoo = 0
    count_gogong = 0
    count_34 = 0
    count_4 = 0
    count_45 = 0

    for line in merged_lines:
        match = re.search(r"(\d+)$", line)
        if not match:
            continue
        v = int(match.group(1))
        if "총계" in line:
            total = v
        elif "정무직계" in line:
            count_jungmoo = v
        elif "고위공무원단" in line:
            count_gogong += v
        elif "부이사관" in line or "3급상당" in line or "4급상당" in line:
            count_34 += v
        elif "서기관" in line and "사무관" in line:
            count_45 += v
        elif "서기관" in line and "사무관" not in line and "부이사관" not in line:
            count_4 += v

    count_5_below = total - (count_jungmoo + count_gogong + count_34 + count_4 + count_45)
    if count_5_below < 0:
        count_5_below = 0

    return {
        "구분": org_name,
        "총정원": total,
        "정무직": count_jungmoo,
        "고공단": count_gogong,
        "3·4급": count_34,
        "4급": count_4,
        "4.5급": count_45,
        "5급이하": count_5_below,
    }
