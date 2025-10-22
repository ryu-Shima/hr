from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Sequence

from .schemas import CandidateProfile, LanguageProficiency
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
    location = None
    for line in lines:
        match = GENDER_LINE_RE.search(line)
        if match:
            gender = match.group(1)
            try:
                age = int(match.group(2))
            except ValueError:
                age = None
            location = match.group(3).split("出力日時")[0].strip()
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

    profile = CandidateProfile(
        provider="bizreach",
        candidate_id=candidate_id,
        gender=gender,
        age=age,
        location=location,
        contact={"email": None, "phone": None},
        education=education,
        experiences=experiences,
        skills=skills,
        languages=languages,
        certifications=certifications,
        awards=awards,
        notes=notes,
        provider_raw={"text": "\n".join(lines).strip(), "fields": provider_fields},
    )
    return profile.model_dump(mode="python")


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
    i = 0
    while i < len(lines):
        stripped = _strip_strikethrough(lines[i].strip())
        if not stripped:
            i += 1
            continue
        if _is_company_header(stripped):
            entry, advance = _parse_company_block(lines, i)
            if entry:
                key = (entry["company"], entry["start"], entry["end"], entry["title"])
                if key not in seen:
                    seen.add(key)
                    experiences.append(entry)
            if advance <= i:
                advance = i + 1
            i = advance
            continue
        i += 1
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
    company_raw = _strip_strikethrough(lines[start_index].strip())
    company = company_raw.strip("【】").strip()
    j = start_index + 1
    prelude: list[str] = []
    title: str = ""
    start: str | None = None
    end: str | None = None
    summary_parts: list[str] = []
    bullets: list[str] = []

    while j < len(lines):
        current_raw = lines[j]
        current = _strip_strikethrough(current_raw.strip())
        if not current:
            j += 1
            continue
        if _is_section_terminator(current) or (_is_company_header(current) and current != company_raw):
            break
        context = _split_date_context(current)
        if context:
            prefix, ctx_start, ctx_end, suffix = context
            if ctx_start:
                start = start or ctx_start
            if ctx_end is not None:
                end = end or ctx_end
            prefix_clean = _clean_context_text(prefix)
            suffix_clean = _clean_context_text(suffix)
            if prefix_clean:
                title = title or prefix_clean
            if suffix_clean:
                summary_parts.append(suffix_clean)
            j += 1
            break
        prelude.append(current)
        j += 1

    department: str | None = None
    if prelude:
        department = _clean_context_text(prelude[0])
        for extra in prelude[1:]:
            cleaned_extra = _clean_context_text(extra)
            if cleaned_extra:
                summary_parts.append(cleaned_extra)

    while j < len(lines):
        current_raw = lines[j]
        current = _strip_strikethrough(current_raw.strip())
        if not current:
            j += 1
            continue
        if _is_section_terminator(current) or _is_company_header(current):
            break
        context = _split_date_context(current)
        if context:
            prefix, ctx_start, ctx_end, suffix = context
            if ctx_start:
                start = start or ctx_start
            if ctx_end is not None:
                end = end or ctx_end
            prefix_clean = _clean_context_text(prefix)
            suffix_clean = _clean_context_text(suffix)
            if prefix_clean and not title:
                title = prefix_clean
            if suffix_clean:
                summary_parts.append(suffix_clean)
            j += 1
            continue
        if BULLET_RE.match(current_raw):
            bullet = BULLET_RE.sub("", current_raw).strip()
            bullet = _clean_context_text(bullet)
            continuation_index = j + 1
            continuation_parts: list[str] = []
            while continuation_index < len(lines):
                continuation_raw = lines[continuation_index]
                continuation = _strip_strikethrough(continuation_raw.strip())
                if not continuation:
                    continuation_index += 1
                    continue
                if (
                    BULLET_RE.match(continuation_raw)
                    or _is_section_terminator(continuation)
                    or _is_company_header(continuation)
                    or _split_date_context(continuation)
                ):
                    break
                cleaned_continuation = _clean_context_text(continuation)
                if cleaned_continuation:
                    continuation_parts.append(cleaned_continuation)
                continuation_index += 1
            if continuation_parts:
                bullet = " ".join([bullet] + continuation_parts).strip()
            if bullet and bullet not in bullets:
                bullets.append(bullet)
            j = continuation_index
            continue
        summary_parts.append(_clean_context_text(current))
        j += 1

    summary_parts = _unique_preserve(summary_parts)
    bullets = _unique_preserve(bullets)

    summary = "\n".join(part for part in summary_parts if part).strip()
    if department:
        dept_line = f"部署: {department}"
        summary = f"{dept_line}\n{summary}" if summary else dept_line
    if not summary and bullets:
        summary = "\n".join(bullets)

    entry = {
        "company": company,
        "title": title or "",
        "start": start,
        "end": end,
        "employment_type": None,
        "summary": summary,
        "bullets": bullets,
    }
    return entry, j


def _is_section_terminator(text: str) -> bool:
    if not text:
        return False
    if text.startswith("##"):
        return True
    clean = text.lstrip("#").strip()
    return bool(CANDIDATE_ID_RE.match(clean))


def _split_date_context(text: str) -> tuple[str, str | None, str | None, str] | None:
    match = DATE_RANGE_CONTEXT_RE.search(text)
    if not match:
        return None
    start = _format_year_month(match.group("start_year"), match.group("start_month"))
    end = None
    if match.group("end_year"):
        end = _format_year_month(match.group("end_year"), match.group("end_month"))
    return match.group("prefix") or "", start, end, match.group("suffix") or ""


def _clean_context_text(text: str) -> str:
    if not text:
        return ""
    cleaned = PAREN_STRIP_RE.sub("", text)
    cleaned = cleaned.strip()
    cleaned = cleaned.strip("：:・-／/　")
    return cleaned.strip()


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


__all__ = ["pdf_to_jsonl", "markdown_to_records"]
