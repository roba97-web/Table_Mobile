"""AI-Test Streamlit 로직을 모바일 앱용 REST API로 노출."""

from __future__ import annotations

import base64
import hashlib
import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

SERVER_ROOT = Path(__file__).resolve().parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from law_center import DEFAULT_LAW_NAME, LawCenterError, fetch_law_bundle  # noqa: E402
from org_list import build_org_dropdown_options  # noqa: E402
from staff_table_fetch import fetch_all_staff_tables_for_org  # noqa: E402
from table_analyze import analyze_staff_table_pdf  # noqa: E402

app = FastAPI(title="정원표 자동 분석기 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FINAL_COLUMNS = ["구분", "총정원", "정무직", "고공단", "3·4급", "4급", "4.5급", "5급이하"]
SUM_COLS = ["총정원", "정무직", "고공단", "3·4급", "4급", "4.5급", "5급이하"]


def _resolve_oc(override: str | None) -> str:
    key = (override or os.environ.get("LAW_OC") or "").strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail=(
                "국가법령정보센터 API 키(LAW_OC)가 없습니다. "
                "server/.env 또는 환경변수 LAW_OC를 설정하세요."
            ),
        )
    return key


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _from_b64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="잘못된 PDF 데이터입니다.") from exc


def build_staff_table_items(pdfs: list) -> list[dict]:
    items: list[dict] = []
    seen_hash: set[str] = set()
    for item in pdfs:
        pdf_hash = hashlib.md5(item.pdf_bytes).hexdigest()
        is_duplicate = pdf_hash in seen_hash
        seen_hash.add(pdf_hash)
        items.append(
            {
                "pdf_bytes": item.pdf_bytes,
                "file_name": item.file_name,
                "law_name": item.law_name,
                "form_title": item.form_title,
                "lsi_seq": item.lsi_seq,
                "pdf_hash": pdf_hash,
                "is_duplicate": is_duplicate,
            }
        )
    return items


class OcBody(BaseModel):
    oc: str | None = None


class FetchStaffBody(BaseModel):
    org_name: str = Field(min_length=1)
    oc: str | None = None


class AnalyzeSelection(BaseModel):
    pdf_base64: str
    label: str = Field(min_length=1)


class AnalyzeBody(BaseModel):
    selections: list[AnalyzeSelection] = Field(min_length=1)
    oc: str | None = None


class ResultPdfBody(BaseModel):
    columns: list[str] = Field(min_length=1)
    rows: list[dict[str, str | int | float]] = Field(min_length=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/step1/load-law")
def load_government_org_law(body: OcBody | None = None) -> dict:
    oc = _resolve_oc(body.oc if body else None)
    try:
        pdf_bytes, lsi_seq, xml_bytes = fetch_law_bundle(DEFAULT_LAW_NAME, oc=oc)
        org_options = build_org_dropdown_options(xml_bytes)
        return {
            "lsi_seq": lsi_seq,
            "pdf_base64": _b64(pdf_bytes),
            "pdf_size": len(pdf_bytes),
            "org_options": org_options,
            "org_count": len(org_options),
        }
    except LawCenterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/step2/fetch-staff")
def fetch_staff_tables(body: FetchStaffBody) -> dict:
    oc = _resolve_oc(body.oc)
    org = body.org_name.strip()
    if not org:
        raise HTTPException(status_code=400, detail="기관명을 선택하세요.")
    try:
        pdfs = fetch_all_staff_tables_for_org(org, oc)
        items = build_staff_table_items(pdfs)
        out: list[dict] = []
        for idx, item in enumerate(items):
            out.append(
                {
                    "index": idx,
                    "form_title": item["form_title"],
                    "file_name": item["file_name"],
                    "law_name": item["law_name"],
                    "lsi_seq": item["lsi_seq"],
                    "pdf_base64": _b64(item["pdf_bytes"]),
                    "is_duplicate": bool(item.get("is_duplicate")),
                    "pdf_hash": item["pdf_hash"],
                }
            )
        dup_cnt = sum(1 for x in items if x.get("is_duplicate"))
        return {
            "items": out,
            "count": len(out),
            "duplicate_count": dup_cnt,
        }
    except LawCenterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/analyze")
def analyze_staff_tables(body: AnalyzeBody) -> dict:
    _resolve_oc(body.oc)
    rows: list[dict] = []
    for sel in body.selections:
        pdf_bytes = _from_b64(sel.pdf_base64)
        row = analyze_staff_table_pdf(sel.label.strip(), pdf_bytes)
        rows.append({k: row[k] for k in FINAL_COLUMNS})

    if len(rows) > 1:
        totals = {col: sum(int(r[col]) for r in rows) for col in SUM_COLS}
        total_row = {"구분": "< 합 계 >", **totals}
        rows = [total_row, *rows]

    return {"columns": FINAL_COLUMNS, "rows": rows}


@app.post("/api/result-pdf")
def result_pdf(body: ResultPdfBody) -> dict:
    try:
        from fpdf import FPDF
        from pdf_font import korean_font_path

        pdf = FPDF(orientation="L", unit="mm", format="A4")
        pdf.set_margins(10, 10, 10)
        pdf.set_auto_page_break(auto=True, margin=10)
        pdf.add_page()
        pdf.add_font("Korean", "", korean_font_path())
        pdf.set_font("Korean", size=11)
        pdf.cell(0, 8, "통합 정원표 분석결과", ln=True)
        pdf.ln(3)

        usable_width = pdf.w - pdf.l_margin - pdf.r_margin
        col_width = usable_width / len(body.columns)

        pdf.set_font("Korean", size=8)
        for col in body.columns:
            pdf.cell(col_width, 8, col, border=1, align="C")
        pdf.ln()

        for row in body.rows:
            for col in body.columns:
                value = row.get(col, "")
                pdf.cell(col_width, 8, str(value), border=1, align="C")
            pdf.ln()

        out = pdf.output()
        data = bytes(out) if isinstance(out, (bytes, bytearray)) else out.encode("latin-1")
        return {
            "file_name": "통합_정원표_분석결과.pdf",
            "pdf_base64": _b64(data),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF 생성 실패: {exc}") from exc
