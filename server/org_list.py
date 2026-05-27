"""정부조직법 본문에서 기관 분류 → 드롭다운 목록 (2단계)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from law_center import LawCenterError

# 국무총리 소속 핵심 기관 (고정)
CORE_PM_ORGS = ("국무조정실", "국무총리비서실")

# 제2조 제2항 7~9호 소속 청
ART2_CHONG_ORGS = (
    "우주항공청",
    "행정중심복합도시건설청",
    "새만금개발청",
)

# 조문 제목에서 제외할 비기관명
EXCLUDE_ARTICLE_NAMES = frozenset({
    "목적",
    "국무회의",
    "부총리",
    "정부위원",
    "행정각부",
})

ARTICLE_TITLE_RE = re.compile(r"^제\d+조(?:의\d+)?\s*\(([가-힣]{2,25})\)")
ART2_COMMITTEE_RE = re.compile(r"따른\s+([가-힣]+위원회)")
CHONG_NAME_RE = re.compile(r"(?<![가-힣])[가-힣]{2,18}청(?![가-힣])")

ADMIN_DEPT_PROVISION_RE = re.compile(
    r"행정각부를\s*(?:다음과\s+같이\s+)?둔다"
)
BU_NAME_RE = re.compile(r"(?<![가-힣])([가-힣]{2,18}부)(?![가-힣])")
BU_NAME_SKIP = frozenset({"행정각부"})

CATEGORY_ORDER = (
    ("국무총리 소속 핵심 기관", "core"),
    ("행정각부를 둔다 조문의 부(部)", "bu"),
    ("국무총리 소속 처(處)", "cheo"),
    ("위원회", "committee"),
    ("행정각부의 청(廳)", "bu_chong"),
    ("제2조 소속 청(廳)", "art2_chong"),
)


def _parse_xml_root(xml_bytes: bytes) -> ET.Element:
    try:
        return ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise LawCenterError("정부조직법 XML 파싱에 실패했습니다.") from exc


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in list(parent)}


def _is_under_buchik(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> bool:
    """부칙·부칙내용 하위 노드면 True (본문 파싱 제외)."""
    current: ET.Element | None = el
    while current is not None and current in parents:
        parent = parents[current]
        if "부칙" in parent.tag:
            return True
        current = parent
    return False


def _main_body_text(root: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    """부칙을 제외한 본문 텍스트만."""
    parts: list[str] = []
    for el in root.iter():
        if _is_under_buchik(el, parents):
            continue
        text = (el.text or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _article_titles(xml_bytes: bytes) -> list[str]:
    root = _parse_xml_root(xml_bytes)
    parents = _parent_map(root)
    names: list[str] = []
    for el in root.iter():
        if _is_under_buchik(el, parents):
            continue
        text = (el.text or "").strip()
        match = ARTICLE_TITLE_RE.match(text)
        if match:
            names.append(match.group(1))
    return names


def _article_blocks(xml_bytes: bytes) -> list[str]:
    root = _parse_xml_root(xml_bytes)
    body = _main_body_text(root, _parent_map(root))
    return [part for part in re.split(r"(?=제\d+조(?:의\d+)?\s*\()", body) if part.strip()]


def _ministries_under_admin_dept_provisions(xml_bytes: bytes) -> list[str]:
    """「행정각부를 둔다」고 규정한 조문 본문에서 OO부 이름을 수집."""
    names: list[str] = []
    seen: set[str] = set()
    for block in _article_blocks(xml_bytes):
        if not ADMIN_DEPT_PROVISION_RE.search(block):
            continue
        for name in BU_NAME_RE.findall(block):
            if name in BU_NAME_SKIP:
                continue
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _article2_block(xml_bytes: bytes) -> str:
    root = _parse_xml_root(xml_bytes)
    parents = _parent_map(root)
    text = _main_body_text(root, parents)
    match = re.search(r"제2조\(.*?(?=제3조\(|$)", text, re.DOTALL)
    return match.group(0) if match else ""


def _parse_article2_committees(block: str) -> list[str]:
    committees: list[str] = []
    seen: set[str] = set()
    for line in block.splitlines():
        if "위원회" not in line or "따른" not in line:
            continue
        match = ART2_COMMITTEE_RE.search(line)
        if match:
            name = match.group(1)
            if name and not name.endswith("청") and name not in seen:
                seen.add(name)
                committees.append(name)
    return committees


def _all_chong_names_in_order(xml_bytes: bytes) -> list[str]:
    """본문 등장 순서대로 청 이름 (부칙 제외)."""
    root = _parse_xml_root(xml_bytes)
    parents = _parent_map(root)
    names: list[str] = []
    seen: set[str] = set()
    for el in root.iter():
        if _is_under_buchik(el, parents):
            continue
        for name in CHONG_NAME_RE.findall(el.text or ""):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def classify_organizations(xml_bytes: bytes) -> dict[str, list[str]]:
    """규칙 6분류로 기관명을 묶습니다."""
    titles = _article_titles(xml_bytes)
    art2 = _article2_block(xml_bytes)

    core = [n for n in CORE_PM_ORGS if n in titles]
    bu = _ministries_under_admin_dept_provisions(xml_bytes)
    cheo: list[str] = []
    cheo_seen: set[str] = set()
    for name in titles:
        if (
            name.endswith("처")
            and name not in EXCLUDE_ARTICLE_NAMES
            and not name.startswith("대통령")
            and name not in cheo_seen
        ):
            cheo_seen.add(name)
            cheo.append(name)
    committee = _parse_article2_committees(art2)

    chong_in_order = _all_chong_names_in_order(xml_bytes)
    chong_set = set(chong_in_order)
    art2_chong = [n for n in ART2_CHONG_ORGS if n in chong_set]
    art2_set = set(art2_chong)

    bu_chong = [name for name in chong_in_order if name not in art2_set]

    return {
        "core": core,
        "bu": bu,
        "cheo": cheo,
        "committee": committee,
        "bu_chong": bu_chong,
        "art2_chong": art2_chong,
    }


def build_org_dropdown_options(xml_bytes: bytes) -> list[str]:
    """selectbox용 기관명 목록 (6분류 순서·분류 내 법령/등장 순, 구분선 없음)."""
    groups = classify_organizations(xml_bytes)
    seen: set[str] = set()
    merged: list[str] = []

    for _, key in CATEGORY_ORDER:
        for name in groups.get(key, []):
            if name not in seen:
                seen.add(name)
                merged.append(name)

    if not merged:
        raise LawCenterError("드롭다운에 넣을 기관을 찾지 못했습니다.")
    return merged
