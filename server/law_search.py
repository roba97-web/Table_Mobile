"""국가법령정보센터 법령 검색·필터."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

from law_center import LAW_API_BASE, LawCenterError, http_get

SEARCH_DISPLAY = 100
MAX_SEARCH_PAGES = 15


def _tag(elem: ET.Element) -> str:
    return elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag


def _law_item_to_dict(item: ET.Element) -> dict[str, str]:
    data: dict[str, str] = {}
    for child in item:
        data[_tag(child)] = (child.text or "").strip()
    return data


def search_law_items(
    query: str,
    oc: str,
    *,
    page: int = 1,
    display: int = SEARCH_DISPLAY,
) -> list[dict[str, str]]:
    if not query.strip():
        raise LawCenterError("검색어가 비어 있습니다.")
    params = {
        "OC": oc.strip(),
        "target": "law",
        "type": "XML",
        "query": query.strip(),
        "display": str(display),
        "page": str(page),
    }
    content = http_get(f"{LAW_API_BASE}/lawSearch.do", params=params)
    raw = content.decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise LawCenterError("법령 검색 XML 파싱에 실패했습니다.") from exc

    code = root.findtext("resultCode") or root.findtext(".//resultCode")
    if code and code != "00":
        msg = root.findtext("resultMsg") or root.findtext(".//resultMsg") or ""
        raise LawCenterError(f"법령 검색 오류({code}): {msg}")

    return [_law_item_to_dict(item) for item in root.findall("law")]


def _is_in_force(item: dict[str, str], today: str) -> bool:
    hist = item.get("현행연혁코드", "")
    if hist and hist != "현행":
        return False
    if "예정" in hist or "예정" in item.get("법령명한글", ""):
        return False
    ef = item.get("시행일자", "")
    return not ef or ef <= today


def matches_org_enforcement_rule(item: dict[str, str], org_name: str, today: str) -> bool:
    name = item.get("법령명한글", "")
    if org_name not in name:
        return False
    if "직제" not in name or "시행규칙" not in name:
        return False
    return _is_in_force(item, today)


def find_org_enforcement_rules(org_name: str, oc: str) -> list[dict[str, str]]:
    """기관명·직제·시행규칙 포함, 현재 시행 중인 시행규칙 전건."""
    org = org_name.strip()
    if not org or org.startswith("("):
        raise LawCenterError("유효한 기관명을 선택하세요.")

    today = date.today().strftime("%Y%m%d")
    seen_mst: set[str] = set()
    matched: list[dict[str, str]] = []

    def collect(items: list[dict[str, str]]) -> None:
        for item in items:
            if not matches_org_enforcement_rule(item, org, today):
                continue
            mst = item.get("법령일련번호", "")
            if mst and mst in seen_mst:
                continue
            if mst:
                seen_mst.add(mst)
            matched.append(item)

    for query in (f"{org} 직제 시행규칙", f"{org} 직제"):
        collect(search_law_items(query, oc))

    for page in range(1, MAX_SEARCH_PAGES + 1):
        items = search_law_items("직제 시행규칙", oc, page=page)
        if not items:
            break
        collect(items)

    if not matched:
        raise LawCenterError(
            f"「{org}」의 현행 「직제 시행규칙」을 찾지 못했습니다. "
            "(기관명·직제·시행규칙 포함, 시행 예정 제외)"
        )
    return matched
