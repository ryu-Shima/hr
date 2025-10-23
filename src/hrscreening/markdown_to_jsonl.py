from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from .schemas import CandidateConstraints, CandidateProfile, LanguageProficiency
from .pdf_utils import extract_markdown

CANDIDATE_ID_RE = re.compile(r"^BU\d{7}$")
GENDER_LINE_RE = re.compile(r"(男性|女性)\s*/\s*(\d+)歳?\s*/\s*([^/]+)")
DATE_LINE_RE = re.compile(r"(\d{4})年(\d{1,2})月\s*[〜~]\s*(?:(\d{4})年(\d{1,2})月|現在)(.*)")
BULLET_RE = re.compile(r"^[・\-]\s?")
STRIKE_RE = re.compile(r"~~([^~]+)~~")
DATE_RANGE_CONTEXT_RE = re.compile(
    r"(?P<prefix>.*?)(?P<start_year>\d{4})年(?P<start_month>\d{1,2})月\s*[〜~\-]\s*"
    r"(?:(?P<end_year>\d{4})年(?P<end_month>\d{1,2})月|現在)(?P<suffix>.*)"
)
PURE_DATE_LINE_RE = re.compile(r"^\s*\d{4}年\d{1,2}月\s*[〜~\-]\s*(?:\d{4}年\d{1,2}月|現在)\s*$")
COMPANY_KEYWORDS = (
    "株式会社",
    "有限会社",
    "合同会社",
    "Inc",
    "INC",
    "inc",
    "LLC",
    "Co.",
    "Corp",
    "Corporation",
    "Company",
    "社団法人",
    "財団法人",
    "学校法人",
)
PAREN_STRIP_RE = re.compile(r"[()（）]")
HOPE_LOCATION_PATTERN = re.compile(r"希望勤務地[：:]\s*(.+)")
SALARY_RANGE_PATTERN = re.compile(
    r"希望年収[：:]\s*(\d+(?:[.,]\d+)?)(?:\s*[万万円]?)\s*[〜~\-ー]\s*(\d+(?:[.,]\d+)?)(?:\s*万円?)",
    re.IGNORECASE,
)
SALARY_SINGLE_PATTERN = re.compile(r"希望年収[：:]\s*(\d+(?:[.,]\d+)?)(?:\s*万円?)", re.IGNORECASE)
SALARY_WORD_PATTERN = re.compile(r"年収\s*(\d+(?:[.,]\d+)?)\s*万円")
RELOCATION_POS_PATTERN = re.compile(r"(転居可|転居可能|転勤可|転勤可能)")
RELOCATION_NEG_PATTERN = re.compile(r"(転居不可|転居困難|転勤不可)")
REMOTE_POS_PATTERN = re.compile(r"(フルリモート|リモート可|在宅勤務可|在宅ワーク可)")
REMOTE_NEG_PATTERN = re.compile(r"(リモート不可|在宅不可)")
HOPE_LOCATION_PATTERN = re.compile(r"希望勤務地[：:]\s*(.+)")

OVERVIEW_KEYS = [
    "所属企業一覧",
    "直近の年収",
    "経験職種",
    "経験業種",
    "マネジメント経験",
    "海外勤務経験",
]
ACADEMICS_KEYS = ["学歴", "語学力", "海外留学経験"]
MAJOR_SECTIONS = {
    "職務要約",
    "コアスキル（活かせる経験・知識・能力）",
    "職務経歴",
    "学歴",
    "表彰",
    "語学・資格",
    "特記事項",
    "フリーテキスト",
}


def pdf_to_jsonl(pdf_path: str | Path, jsonl_path: str | Path, *, markdown_path: str | Path | None = None) -> None:
    pdf_path = Path(pdf_path)
    markdown = extract_markdown(pdf_path)
    if markdown_path is not None:
        Path(markdown_path).write_text(markdown, encoding="utf-8")
    records = list(markdown_to_records(markdown))
    if not records:
        raise ValueError("No candidates detected in markdown.")
    lines = [json.dumps({"provider": "bizreach", "payload": record}, ensure_ascii=False) for record in records]
    Path(jsonl_path).write_text("\n".join(lines), encoding="utf-8")


def markdown_to_records(markdown: str) -> Iterable[dict]:
    for candidate_id, lines in _split_candidates(markdown):
        yield _lines_to_candidate(candidate_id, lines)


def _split_candidates(markdown: str) -> Iterable[tuple[str, list[str]]]:
    current_id: str | None = None
    buffer: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        clean = stripped.lstrip('#').strip()
        clean = _strip_strikethrough(clean)
        match = CANDIDATE_ID_RE.match(clean)
        if match:
            new_id = clean
            if current_id is None:
                current_id = new_id
                continue
            if new_id != current_id:
                if buffer:
                    yield current_id, _normalize_lines(buffer)
                buffer = []
                current_id = new_id
            continue
        if current_id is not None:
            buffer.append(line)
    if current_id is not None and buffer:
        yield current_id, _normalize_lines(buffer)


def _normalize_lines(lines: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    previous: str | None = None
    for line in lines:
        if line == previous:
            continue
        normalized.append(line)
        previous = line
    return normalized


def _lines_to_candidate(candidate_id: str, lines: list[str]) -> dict:
    sections = _parse_sections(lines)

    gender = None
    age = None
    for line in lines:
        match = GENDER_LINE_RE.search(line)
        if match:
            gender = match.group(1)
            try:
                age = int(match.group(2))
            except ValueError:
                age = None
            break

    overview_data = _extract_keyed_items(sections.get("職務経歴概要", []), OVERVIEW_KEYS)
    academic_overview = _extract_keyed_items(sections.get("学歴/語学", []), ACADEMICS_KEYS)

    exp_lines = sections.get("職務経歴") or []
    experiences = _extract_experiences(exp_lines)
    if not experiences and "職務要約" in sections:
        experiences = _extract_experiences(sections["職務要約"])
    if not experiences:
        experiences = _extract_experiences(lines)
    skills = _extract_skills_from_section(sections.get("コアスキル（活かせる経験・知識・能力）", []))
    education = _extract_education(sections.get("学歴", []))
    awards = _extract_bullets(sections.get("表彰", []))
    languages, certifications = _extract_languages_and_certifications(sections.get("語学・資格", []))

    notes_parts = []
    for heading in ("特記事項", "特記事項 フリーテキスト", "フリーテキスト"):
        if heading in sections:
            notes_parts.append(_section_text(sections[heading]))
    notes = "\n\n".join([p for p in notes_parts if p]) or None

    provider_fields = {}
    for heading in MAJOR_SECTIONS.union({"職務経歴概要", "学歴/語学"}):
        if heading in sections:
            provider_fields[heading] = _section_text(sections[heading])
    if overview_data:
        provider_fields["職務経歴概要"] = overview_data
    if academic_overview:
        provider_fields["学歴/語学"] = academic_overview

    desired_locations = _extract_desired_locations(sections)
    can_relocate, remote_ok = _extract_special_constraints(sections)
    desired_salary_min, desired_salary_max = _extract_desired_salary(sections)

    constraints_kwargs: dict[str, Any] = {}
    if desired_locations:
        constraints_kwargs["location"] = desired_locations
    if can_relocate is not None:
        constraints_kwargs["can_relocate"] = can_relocate
    if remote_ok is not None:
        constraints_kwargs["remote_ok"] = remote_ok
    constraints = CandidateConstraints(**constraints_kwargs) if constraints_kwargs else None

    profile = CandidateProfile(
        provider="bizreach",
        candidate_id=candidate_id,
        gender=gender,
        age=age,
        contact={"email": None, "phone": None},
        education=education,
        experiences=experiences,
        skills=skills,
        languages=languages,
        certifications=certifications,
        awards=awards,
        notes=notes,
        provider_raw={"text": "\n".join(lines).strip(), "fields": provider_fields},
        constraints=constraints,
        desired_salary_min_jpy=desired_salary_min,
        desired_salary_max_jpy=desired_salary_max,
    )
    raw = profile.model_dump(mode="python", exclude_none=True)
    return _prune_empty(raw)


def _parse_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    buffer: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("##"):
            if current is not None and buffer:
                sections[current] = buffer
            heading = stripped.lstrip('#').strip()
            heading = _strip_strikethrough(heading)
            current = heading
            buffer = []
            continue
        if stripped.startswith('#'):
            continue
        if current is not None:
            buffer.append(line)
    if current is not None and buffer:
        sections[current] = buffer
    return sections


def _section_text(section_lines: Sequence[str]) -> str:
    return "\n".join(_strip_strikethrough(line.strip()) for line in section_lines).strip()


def _extract_keyed_items(section_lines: Sequence[str], keys: Sequence[str]) -> dict[str, str]:
    if not section_lines:
        return {}
    result: dict[str, str] = {}
    current_key: str | None = None
    buffer: list[str] = []
    key_set = set(keys)
    for line in section_lines:
        stripped = _strip_strikethrough(line.strip())
        if stripped.startswith("【") and "】" in stripped:
            key = stripped.strip("【】").strip()
            if key in key_set:
                if current_key and buffer:
                    result[current_key] = "\n".join(buffer).strip()
                current_key = key
                buffer = []
                continue
        if current_key:
            buffer.append(stripped)
    if current_key and buffer:
        result[current_key] = "\n".join(buffer).strip()
    return result


def _extract_bullets(section_lines: Sequence[str]) -> list[str]:
    items: list[str] = []
    for line in section_lines or []:
        stripped = _strip_strikethrough(line.strip())
        if stripped.startswith("・") or stripped.startswith("-"):
            entry = stripped.lstrip("・- ").strip()
            if entry:
                items.append(entry)
    return items


def _extract_skills_from_section(section_lines: Sequence[str]) -> list[str]:
    skills: list[str] = []
    for line in section_lines or []:
        stripped = _strip_strikethrough(line.strip())
        if stripped.startswith('【'):
            break
        if stripped.startswith('・') or stripped.startswith('-'):
            entry = stripped.lstrip('・- ').strip()
            if entry:
                skills.append(entry)
    return skills


def _extract_education(section_lines: Sequence[str]) -> list[dict]:
    entries = []
    for item in _extract_bullets(section_lines):
        entries.append({"school": item, "major": None, "degree": None, "start": None, "end": None})
    return entries


def _extract_languages_and_certifications(section_lines: Sequence[str]) -> tuple[list[LanguageProficiency], list[str]]:
    languages: list[LanguageProficiency] = []
    certifications: list[str] = []
    for item in _extract_bullets(section_lines):
        tokens = item.split()
        if not tokens:
            continue
        language = tokens[0]
        level = " ".join(tokens[1:]) or None
        if language.endswith("語"):
            languages.append(LanguageProficiency(language=language, level=level))
        else:
            certifications.append(item)
    return [lp.model_dump(mode="python") for lp in languages], certifications




def _extract_experiences(section_lines: Sequence[str]) -> list[dict]:
    experiences: list[dict] = []
    if not section_lines:
        return experiences
    lines = list(section_lines)
    seen: set[tuple[str | None, str | None, str | None, str | None]] = set()
    index = 0
    while index < len(lines):
        stripped = _strip_strikethrough(lines[index].strip())
        if not stripped:
            index += 1
            continue
        if _is_company_header(stripped):
            entry, next_index = _parse_company_block(lines, index)
            if entry:
                key = (entry["company"], entry["start"], entry["end"], entry["title"])
                if key not in seen:
                    seen.add(key)
                    experiences.append(entry)
            if next_index <= index:
                next_index = index + 1
            index = next_index
            continue
        index += 1
    return experiences


def _is_company_header(line: str) -> bool:
    cleaned = line.strip()
    if not cleaned:
        return False
    if cleaned.startswith("##"):
        return False
    if cleaned.startswith("【") and "】" in cleaned:
        inner = cleaned.strip("【】").strip()
        return any(keyword in inner for keyword in COMPANY_KEYWORDS)
    if cleaned.startswith("・") or cleaned.startswith("-"):
        return False
    return any(keyword in cleaned for keyword in COMPANY_KEYWORDS)


def _parse_company_block(lines: Sequence[str], start_index: int) -> tuple[dict | None, int]:
    raw_company = lines[start_index]
    company_line = _strip_strikethrough(raw_company.strip())
    company_name, line_start, line_end = _split_company_line(company_line)
    company = company_name or company_line.strip("【】").strip()

    index = start_index + 1
    title: str = ""
    start = line_start
    end = line_end

    # capture department / title line
    index = _skip_blank_lines(lines, index)
    if index < len(lines):
        dept_candidate_raw = lines[index]
        dept_candidate = _strip_strikethrough(dept_candidate_raw.strip())
        if dept_candidate and not _contains_date(dept_candidate) and not _is_company_header(dept_candidate):
            title = _clean_context_text(dept_candidate)
            index += 1

    index = _skip_blank_lines(lines, index)

    # optional job line containing dates (to skip from summary but use for dates)
    if index < len(lines):
        role_line_raw = lines[index]
        role_line = _strip_strikethrough(role_line_raw.strip())
        role_start, role_end = _extract_dates_from_text(role_line)
        if role_start or role_end:
            if start is None:
                start = role_start
            if end is None:
                end = role_end
            # skip this line entirely from summary per spec
            index += 1

    summary_lines: list[str] = []

    while index < len(lines):
        raw_line = lines[index]
        stripped = _strip_strikethrough(raw_line.strip())
        if not stripped:
            summary_lines.append("")
            index += 1
            continue
        if _is_section_terminator(stripped) or _is_company_header(stripped):
            break
        if PURE_DATE_LINE_RE.match(stripped):
            index += 1
            continue
        summary_line = _clean_summary_line(raw_line)
        summary_lines.append(summary_line)
        index += 1

    summary_text = "\n".join(line for line in summary_lines if line is not None).strip()
    bullets: list[str] = []

    entry = {
        "company": company,
        "title": title,
        "start": start,
        "end": end,
        "employment_type": None,
        "summary": summary_text,
        "bullets": bullets,
    }
    return entry, index


def _is_section_terminator(text: str) -> bool:
    if not text:
        return False
    if text.startswith("##"):
        return True
    clean = text.lstrip("#").strip()
    return bool(CANDIDATE_ID_RE.match(clean))


def _skip_blank_lines(lines: Sequence[str], index: int) -> int:
    while index < len(lines):
        candidate = _strip_strikethrough(lines[index].strip())
        if candidate:
            break
        index += 1
    return index


def _split_company_line(text: str) -> tuple[str, str | None, str | None]:
    start = None
    end = None
    match = DATE_RANGE_CONTEXT_RE.search(text)
    if match:
        start = _format_year_month(match.group("start_year"), match.group("start_month"))
        if match.group("end_year"):
            end = _format_year_month(match.group("end_year"), match.group("end_month"))
        remaining = f"{match.group('prefix') or ''}{match.group('suffix') or ''}"
        company = remaining.strip()
    else:
        company = text
    company = company.strip("【】").strip()
    return company, start, end


def _split_date_context(text: str) -> tuple[str, str | None, str | None, str] | None:
    match = DATE_RANGE_CONTEXT_RE.search(text)
    if not match:
        return None
    start = _format_year_month(match.group("start_year"), match.group("start_month"))
    end = None
    if match.group("end_year"):
        end = _format_year_month(match.group("end_year"), match.group("end_month"))
    return match.group("prefix") or "", start, end, match.group("suffix") or ""


def _extract_dates_from_text(text: str) -> tuple[str | None, str | None]:
    match = DATE_RANGE_CONTEXT_RE.search(text)
    if not match:
        return None, None
    start = _format_year_month(match.group("start_year"), match.group("start_month"))
    end = None
    if match.group("end_year"):
        end = _format_year_month(match.group("end_year"), match.group("end_month"))
    return start, end


def _clean_context_text(text: str) -> str:
    if not text:
        return ""
    cleaned = PAREN_STRIP_RE.sub("", text)
    cleaned = cleaned.strip()
    cleaned = cleaned.strip("：:・-／/　")
    return cleaned.strip()


def _clean_summary_line(text: str) -> str:
    cleaned = _strip_strikethrough(text)
    return cleaned.strip()


def _extract_special_constraints(sections: dict[str, list[str]]) -> tuple[bool | None, bool | None]:
    can_relocate: bool | None = None
    remote_ok: bool | None = None
    for lines in sections.values():
        for raw_line in lines:
            stripped = _strip_strikethrough(raw_line.strip())
            if not stripped:
                continue
            if RELOCATION_NEG_PATTERN.search(stripped):
                can_relocate = False
            elif RELOCATION_POS_PATTERN.search(stripped) and can_relocate is None:
                can_relocate = True
            if REMOTE_NEG_PATTERN.search(stripped):
                remote_ok = False
            elif REMOTE_POS_PATTERN.search(stripped) and remote_ok is None:
                remote_ok = True
    return can_relocate, remote_ok


def _extract_desired_salary(sections: dict[str, list[str]]) -> tuple[int | None, int | None]:
    salary_min: int | None = None
    salary_max: int | None = None
    for lines in sections.values():
        for raw_line in lines:
            stripped = _strip_strikethrough(raw_line.strip())
            if not stripped:
                continue
            if salary_min is None or salary_max is None:
                range_match = SALARY_RANGE_PATTERN.search(stripped)
                if range_match:
                    salary_min = _salary_to_int(range_match.group(1))
                    salary_max = _salary_to_int(range_match.group(2))
                    continue
            if salary_min is None and salary_max is None:
                single_match = SALARY_SINGLE_PATTERN.search(stripped)
                if single_match:
                    value = _salary_to_int(single_match.group(1))
                    salary_min = salary_max = value
                    continue
            if salary_min is None and salary_max is None:
                generic_match = SALARY_WORD_PATTERN.search(stripped)
                if generic_match:
                    value = _salary_to_int(generic_match.group(1))
                    salary_min = salary_max = value
    return salary_min, salary_max


def _salary_to_int(value: str) -> int:
    normalized = value.replace(",", "")
    amount = float(normalized)
    return int(amount * 10000)


def _extract_desired_locations(sections: dict[str, list[str]]) -> list[str]:
    locations: list[str] = []
    for lines in sections.values():
        for raw_line in lines:
            stripped = _strip_strikethrough(raw_line.strip())
            if not stripped:
                continue
            match = HOPE_LOCATION_PATTERN.search(stripped)
            if not match:
                continue
            tokens = re.split(r"[、,/・\s]+", match.group(1))
            for token in tokens:
                cleaned = token.strip()
                if cleaned:
                    locations.append(cleaned)
    return _unique_preserve(locations)


def _unique_preserve(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _strip_strikethrough(text: str) -> str:
    return STRIKE_RE.sub(r"\1", text)
def _format_year_month(year: str, month: str) -> str:
    return f"{int(year):04d}-{int(month):02d}"

def _prune_empty(value):
    if isinstance(value, dict):
        result: dict = {}
        for key, item in value.items():
            cleaned = _prune_empty(item)
            if cleaned in (None, "", [], {}):
                continue
            result[key] = cleaned
        return result
    if isinstance(value, list):
        cleaned_list = []
        for item in value:
            cleaned = _prune_empty(item)
            if cleaned in (None, "", [], {}):
                continue
            cleaned_list.append(cleaned)
        return cleaned_list
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else ""
    return value


def _contains_date(text: str) -> bool:
    return bool(DATE_RANGE_CONTEXT_RE.search(text))


__all__ = ["pdf_to_jsonl", "markdown_to_records"]
