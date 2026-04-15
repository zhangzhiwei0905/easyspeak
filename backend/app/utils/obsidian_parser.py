"""Obsidian Markdown parser - extract structured data from daily push files."""
import re
import os
from datetime import date, datetime
from typing import Optional
from app.schemas.daily import ContentImport, PhraseImport, WordImport, PhraseExample


def parse_obsidian_file(filepath: str) -> ContentImport:
    """Parse a single Obsidian markdown file into structured data."""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.split("\n")

    # Parse header: # ☀️ 2026-04-14 咖啡店点单 (Ordering at a Coffee Shop)
    header_match = re.match(r"^#.*?(\d{4}-\d{2}-\d{2})\s+(.+?)\s*\((.+?)\)\s*$", lines[0])
    if not header_match:
        raise ValueError(f"Cannot parse header: {lines[0]}")

    push_date = date.fromisoformat(header_match.group(1))
    theme_zh = header_match.group(2).strip()
    theme_en = header_match.group(3).strip() if header_match.group(3) else ""

    # Determine time_slot from emoji
    time_slot = "morning" if "☀️" in lines[0] else "evening"

    # Parse introduction (paragraph after header, before first ---)
    introduction = ""
    intro_lines = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.strip():
            intro_lines.append(line.strip())
    introduction = " ".join(intro_lines)

    # Parse phrases (## 1. phrase_name or ## N. phrase_name)
    phrases = _parse_phrases(text)

    # Parse words table
    words = _parse_words_table(text)

    # Parse practice tips
    practice_tips = _parse_practice_tips(text)

    return ContentImport(
        date=push_date,
        time_slot=time_slot,
        theme_zh=theme_zh,
        theme_en=theme_en,
        introduction=introduction if introduction else None,
        practice_tips=practice_tips,
        phrases=phrases,
        words=words,
    )


def _parse_phrases(text: str) -> list[PhraseImport]:
    """Extract phrases from markdown text. Handles two formats."""
    phrases = []

    # Split by phrase sections (## N. ...)
    sections = re.split(r"\n##\s+\d+\.\s+", text)
    # First section is header/intro, skip
    for section in sections[1:]:
        # Each section may contain later sections (📚, 💡), but the phrase content
        # is before the first --- separator. Truncate to avoid leaking.
        phrase_section = section.split("\n---\n")[0] if "\n---\n" in section else section

        phrase = _parse_single_phrase(phrase_section)
        if phrase:
            phrases.append(phrase)

    return phrases


def _parse_single_phrase(section: str) -> Optional[PhraseImport]:
    """Parse a single phrase section."""
    lines = section.strip().split("\n")
    if not lines:
        return None

    # First line is the phrase name
    phrase_name = lines[0].strip()
    if not phrase_name:
        return None

    full_text = "\n".join(lines)

    # Extract explanation
    explanation = ""
    expl_match = re.search(r"\*\*📖 解读\*\*\s*\n(.*?)(?=\n-|\n\*\*例句|\n>\s)", full_text, re.DOTALL)
    if not expl_match:
        # Try alternative format (no bold markers)
        expl_match = re.search(r"📖\s*解读\s*\n(.*?)(?=\n-|\n例句|\n>)", full_text, re.DOTALL)
    if expl_match:
        explanation = expl_match.group(1).strip()

    # Extract examples - Format 1: - *"English"* \n （Chinese）
    examples = []
    example_pattern_1 = re.findall(
        r'-\s*\*"([^"]+)"\*\s*\n\s*（([^）]+)）',
        full_text,
    )
    for en, cn in example_pattern_1:
        examples.append(PhraseExample(en=en.strip(), cn=cn.strip()))

    # Format 2: **例句 N：** \n > English \n > （Chinese）
    if not examples:
        example_pattern_2 = re.findall(
            r"\*\*例句\s*\d+[：:]\*\*\s*\n>\s*(.*?)\s*\n>\s*（(.*?)）",
            full_text,
        )
        for en, cn in example_pattern_2:
            examples.append(PhraseExample(en=en.strip(), cn=cn.strip()))

    # Extract source
    source = ""
    source_match = re.search(r"💬\s*来源[：:]\s*[《*]*(.*?)[》*\n]", full_text)
    if source_match:
        source = source_match.group(1).strip()

    return PhraseImport(
        phrase=phrase_name,
        explanation=explanation,
        examples=examples,
        source=source if source else None,
    )


def _parse_words_table(text: str) -> list[WordImport]:
    """Extract words from markdown table."""
    words = []
    # Find table rows: | N | word | phonetic | pos | meaning | example |
    table_match = re.search(
        r"\|[-\s|]+\|\n((?:\|\s*\d+\s*\|.*?\|\s*\n)+)",
        text,
    )
    if not table_match:
        return words

    rows = table_match.group(1).strip().split("\n")
    for row in rows:
        cells = [c.strip() for c in row.split("|")]
        # cells: ['', '1', 'word', '/phonetic/', 'n.', 'meaning', 'example', '']
        if len(cells) >= 7 and cells[1].isdigit():
            words.append(
                WordImport(
                    word=cells[2],
                    phonetic=cells[3],
                    part_of_speech=cells[4],
                    meaning=cells[5],
                    example=cells[6],
                )
            )

    return words


def _parse_practice_tips(text: str) -> Optional[str]:
    """Extract practice tips section."""
    match = re.search(
        r"##\s*💡\s*今日练习建议\s*\n(.*?)(?=\n##|\n---|\Z)",
        text,
        re.DOTALL,
    )
    if match:
        tips = match.group(1).strip()
        return tips if tips else None
    return None


def parse_all_obsidian_files(directory: str) -> list[ContentImport]:
    """Parse all .md files in a directory."""
    results = []
    if not os.path.exists(directory):
        return results

    for filename in sorted(os.listdir(directory)):
        if filename.endswith(".md"):
            filepath = os.path.join(directory, filename)
            try:
                data = parse_obsidian_file(filepath)
                results.append(data)
                print(f"  ✅ Parsed: {filename} ({len(data.phrases)} phrases, {len(data.words)} words)")
            except Exception as e:
                print(f"  ❌ Failed: {filename} - {e}")

    return results
