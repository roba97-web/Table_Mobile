"""시행규칙 별표·서식 중 정원표 PDF 조회."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urljoin

from law_center import LawCenterError, fetch_law_xml, http_get
from law_search import find_org_enforcement_rules

LAW_HOST = "http://www.law.go.kr"


@dataclass
class StaffTableForm:
    title: str
    pdf_path: str

    @property
    def pdf_url(self) -> str:
        return urljoin(LAW_HOST, self.pdf_path)


@dataclass
class StaffTablePdf:
    pdf_bytes: bytes
    file_name: str
    law_name: str
    form_title: str
    lsi_seq: str


def _tag(elem: ET.Element) -> str:
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


def find_staff_table_forms(xml_bytes: bytes) -> list[StaffTableForm]:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise LawCenterError("시행규칙 XML 파싱에 실패했습니다.") from exc

    forms: list[StaffTableForm] = []
    for unit in root.iter():
        if _tag(unit) != "별표단위":
            continue
        title = (unit.findtext("별표제목") or "").strip()
        if "정원표" not in title:
            continue
        pdf_path = (
            unit.findtext("별표서식PDF파일링크")
            or unit.findtext("별표PDF파일링크")
            or ""
        ).strip()
        if not pdf_path:
            continue
        forms.append(StaffTableForm(title=title, pdf_path=pdf_path))
    return forms


def download_form_pdf(form: StaffTableForm) -> bytes:
    content = http_get(form.pdf_url)
    if not content.startswith(b"%PDF"):
        raise LawCenterError(f"정원표 PDF를 받지 못했습니다: {form.title}")
    return content


def _safe_file_name(form_title: str, duplicate_index: int = 0) -> str:
    base = re.sub(r'[\\/:*?"<>|]', "_", form_title.strip())[:120]
    if duplicate_index:
        return f"{base}_{duplicate_index}.pdf"
    return f"{base}.pdf"


def fetch_all_staff_tables_for_org(org_name: str, oc: str) -> list[StaffTablePdf]:
    """매칭 시행규칙·정원표 별표의 PDF를 모두 수집."""
    org = org_name.strip()
    rules = find_org_enforcement_rules(org, oc)
    results: list[StaffTablePdf] = []
    title_counts: dict[str, int] = {}

    for rule in rules:
        law_name = rule.get("법령명한글", org)
        lsi_seq = rule.get("법령일련번호", "")
        if not lsi_seq:
            continue

        xml_bytes = fetch_law_xml(lsi_seq, oc)
        for form in find_staff_table_forms(xml_bytes):
            pdf_bytes = download_form_pdf(form)
            title_key = form.title.strip()
            title_counts[title_key] = title_counts.get(title_key, 0) + 1
            dup = title_counts[title_key] - 1
            results.append(
                StaffTablePdf(
                    pdf_bytes=pdf_bytes,
                    file_name=_safe_file_name(form.title, dup),
                    law_name=law_name,
                    form_title=form.title,
                    lsi_seq=lsi_seq,
                )
            )

    if not results:
        raise LawCenterError(
            f"「{org}」 시행규칙에서 「정원표」 별표·서식 PDF를 찾지 못했습니다."
        )
    return results


def fetch_staff_table_for_org(org_name: str, oc: str) -> tuple[bytes, str, str, str]:
    """하위 호환 — 첫 번째 PDF만 반환."""
    items = fetch_all_staff_tables_for_org(org_name, oc)
    first = items[0]
    return first.pdf_bytes, first.law_name, first.form_title, first.lsi_seq
