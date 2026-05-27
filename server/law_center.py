"""국가법령정보센터 — 법령명 검색 후 Open API XML → PDF (1단계)."""

from __future__ import annotations

import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import httpx
from fpdf import FPDF

LAW_API_BASE = "http://www.law.go.kr/DRF"
DEFAULT_LAW_NAME = "정부조직법"
MAX_RETRIES = 3
RETRY_DELAY_SEC = 1.5
MAX_PDF_CHARS = 400_000
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/xml, text/xml, */*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "http://www.law.go.kr/",
    "Connection": "close",
}


class LawCenterError(Exception):
    """국가법령정보센터 연동 오류."""


def _build_url(base: str, params: dict[str, str] | None) -> str:
    if not params:
        return base
    query = urllib.parse.urlencode(params)
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{query}"


def _fetch_urllib(url: str, extra_headers: dict[str, str] | None = None) -> bytes:
    headers = {**REQUEST_HEADERS, **(extra_headers or {})}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def _fetch_httpx(url: str, extra_headers: dict[str, str] | None = None) -> bytes:
    headers = {**REQUEST_HEADERS, **(extra_headers or {})}
    with httpx.Client(
        timeout=90.0,
        follow_redirects=True,
        http2=False,
        headers=headers,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def http_get(url: str, params: dict[str, str] | None = None, extra_headers: dict[str, str] | None = None) -> bytes:
    """국가법령정보센터 요청 (재시도 + urllib 폴백)."""
    full_url = _build_url(url, params)
    errors: list[str] = []

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return _fetch_httpx(full_url, extra_headers)
        except httpx.HTTPStatusError as exc:
            errors.append(f"httpx({attempt}): {exc}")
            if exc.response.status_code in (400, 401, 403, 404):
                break
            time.sleep(RETRY_DELAY_SEC * attempt)
        except Exception as exc:
            errors.append(f"httpx({attempt}): {exc}")
            time.sleep(RETRY_DELAY_SEC * attempt)

    try:
        return _fetch_urllib(full_url, extra_headers)
    except urllib.error.HTTPError as exc:
        raise LawCenterError(f"HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        errors.append(f"urllib: {exc}")
        reason = str(exc.reason) if getattr(exc, "reason", None) else str(exc)
        if "getaddrinfo failed" in reason or "11001" in reason:
            raise LawCenterError(
                "www.law.go.kr 주소를 찾을 수 없습니다(DNS 오류). "
                "인터넷 연결·DNS 설정을 확인해 주세요."
            ) from exc
        raise LawCenterError(
            "법령정보센터 연결이 끊겼습니다. 잠시 후 다시 시도하거나 "
            "방화벽·VPN·회사망 차단 여부를 확인해 주세요.\n"
            + " / ".join(errors[-3:])
        ) from exc
    except Exception as exc:
        raise LawCenterError(f"요청 실패: {exc}") from exc


def find_lsi_seq(law_name: str, oc: str = "test") -> str:
    """법령명으로 검색해 현행 법령의 lsiSeq(법령일련번호)를 반환."""
    if not law_name.strip():
        raise LawCenterError("법령명이 비어 있습니다.")
    if not oc.strip():
        raise LawCenterError("API 인증값(OC)이 필요합니다. open.law.go.kr에서 발급 후 설정하세요.")

    params = {
        "OC": oc.strip(),
        "target": "law",
        "type": "XML",
        "query": law_name.strip(),
        "display": 20,
    }

    try:
        content = http_get(f"{LAW_API_BASE}/lawSearch.do", params=params)
    except LawCenterError:
        raise
    except Exception as exc:
        raise LawCenterError(f"법령 검색 요청 실패: {exc}") from exc

    raw = content.decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise LawCenterError("법령 검색 응답(XML)을 읽을 수 없습니다.") from exc

    result_code = root.findtext("resultCode") or root.findtext(".//resultCode")
    if result_code and result_code != "00":
        msg = root.findtext("resultMsg") or root.findtext(".//resultMsg") or ""
        raise LawCenterError(f"법령 검색 오류({result_code}): {msg}")

    items = root.findall(".//law") or root.findall(".//Law")
    if not items:
        raise LawCenterError(f"「{law_name}」 검색 결과가 없습니다.")

    target = law_name.strip()

    def _lsi_from_item(item: ET.Element) -> str | None:
        for child in item:
            text = (child.text or "").strip()
            if "MST=" in text:
                match = re.search(r"MST=(\d+)", text)
                if match:
                    return match.group(1)
            if child.tag in ("법령일련번호", "lsiSeq") and text.isdigit():
                return text
        block = ET.tostring(item, encoding="unicode")
        match = re.search(r"MST=(\d+)", block)
        return match.group(1) if match else None

    for item in items:
        block = ET.tostring(item, encoding="unicode")
        if target not in block:
            continue
        lsi = _lsi_from_item(item)
        if lsi:
            return lsi

    if len(items) == 1:
        lsi = _lsi_from_item(items[0])
        if lsi:
            return lsi

    match = re.search(
        rf"<!\[CDATA\[{re.escape(target)}\]\]>[\s\S]*?MST=(\d+)",
        raw,
    )
    if match:
        return match.group(1)

    raise LawCenterError(f"「{law_name}」의 법령일련번호(lsiSeq)를 찾지 못했습니다.")


def fetch_law_xml(lsi_seq: str, oc: str) -> bytes:
    """Open API로 법령 본문 XML을 받습니다."""
    params = {
        "OC": oc.strip(),
        "target": "law",
        "MST": lsi_seq.strip(),
        "type": "XML",
    }
    content = http_get(f"{LAW_API_BASE}/lawService.do", params=params)
    if b"<" not in content[:500]:
        raise LawCenterError("법령 본문 XML 응답이 비어 있습니다.")
    return content


def extract_text_from_law_xml(xml_bytes: bytes) -> str:
    """법령 XML에서 본문 텍스트를 추출합니다."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise LawCenterError("법령 본문 XML 파싱에 실패했습니다.") from exc

    lines = []
    for elem in root.iter():
        text = (elem.text or "").strip()
        if text:
            lines.append(text)
    body = "\n".join(lines)
    if not body.strip():
        raise LawCenterError("법령 본문 텍스트를 추출하지 못했습니다.")
    return body


def _korean_font_path() -> str:
    from pdf_font import korean_font_path

    try:
        return korean_font_path()
    except OSError as exc:
        raise LawCenterError(str(exc)) from exc


def build_pdf_from_text(text: str, title: str) -> bytes:
    """추출한 법령 텍스트를 PDF로 만듭니다."""
    if len(text) > MAX_PDF_CHARS:
        text = text[:MAX_PDF_CHARS] + "\n\n...(용량 제한으로 일부 생략)"

    font_path = _korean_font_path()
    pdf = FPDF()
    pdf.set_margins(12, 12, 12)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.add_font("Korean", "", font_path)
    pdf.set_font("Korean", size=9)
    width = pdf.epw
    pdf.multi_cell(width, 6, title)
    pdf.ln(3)

    for line in text.split("\n"):
        if pdf.get_y() > 275:
            pdf.add_page()
            pdf.set_font("Korean", size=9)
        safe = line.replace("\r", "").replace("\t", " ")[:800]
        if not safe:
            pdf.ln(2)
            continue
        # 긴 줄·공백 없는 토큰은 잘라서 출력
        chunks = [safe[i : i + 120] for i in range(0, len(safe), 120)]
        for chunk in chunks:
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(width, 5, chunk)

    out = pdf.output()
    data = bytes(out) if isinstance(out, (bytes, bytearray)) else out.encode("latin-1")
    if not data.startswith(b"%PDF"):
        raise LawCenterError("PDF 생성에 실패했습니다.")
    return data


def download_law_pdf(lsi_seq: str, law_name: str = DEFAULT_LAW_NAME, oc: str = "test") -> bytes:
    """
    국가법령정보센터 Open API로 본문 XML을 받아 PDF로 변환합니다.
    (웹사이트 lsDownPdf.do 는 공개 URL이 없어 404 발생)
    """
    xml_bytes = fetch_law_xml(lsi_seq, oc=oc)
    text = extract_text_from_law_xml(xml_bytes)
    return build_pdf_from_text(text, title=law_name)


def fetch_law_pdf(law_name: str = DEFAULT_LAW_NAME, oc: str = "test") -> tuple[bytes, str]:
    """법령명 → lsiSeq 조회 → XML 수신 → PDF 생성. (pdf_bytes, lsi_seq) 반환."""
    pdf_bytes, lsi_seq, _ = fetch_law_bundle(law_name, oc=oc)
    return pdf_bytes, lsi_seq


def fetch_law_bundle(
    law_name: str = DEFAULT_LAW_NAME, oc: str = "test"
) -> tuple[bytes, str, bytes]:
    """(pdf_bytes, lsi_seq, xml_bytes) — XML은 기관목록 파싱에 재사용."""
    lsi_seq = find_lsi_seq(law_name, oc=oc)
    xml_bytes = fetch_law_xml(lsi_seq, oc=oc)
    text = extract_text_from_law_xml(xml_bytes)
    pdf_bytes = build_pdf_from_text(text, title=law_name)
    return pdf_bytes, lsi_seq, xml_bytes
