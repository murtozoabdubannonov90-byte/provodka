"""Hujjatlar papkasidan oxirgi ishonchnomani topib, ishonchli shaxs
ma'lumotlarini (F.I.Sh., lavozim, pasport seriya-raqami) ajratib oladi.

Ma'lumotlar o'zgartirilmasdan, hujjatdagi ko'rinishida qaytariladi.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any

DOC_EXTENSIONS = (".docx", ".xlsx", ".pdf", ".txt", ".json")

NAME_HINTS = ("ishonchnoma", "ishonchnama", "doverennost", "доверенн", "m-2", "м-2")


@dataclass
class TrustedPerson:
    fio: str = ""
    position: str = ""
    passport: str = ""
    pinfl: str = ""
    doc_number: str = ""
    source_file: str = ""
    context: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def missing(self) -> list[str]:
        labels = {"fio": "F.I.Sh.", "position": "lavozim", "passport": "pasport"}
        return [label for key, label in labels.items() if not getattr(self, key)]


# --------------------------------------------------------------------------
# Matn ajratish
# --------------------------------------------------------------------------

def extract_text(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".docx"):
        return _text_docx(path)
    if lower.endswith(".xlsx"):
        return _text_xlsx(path)
    if lower.endswith(".pdf"):
        return _text_pdf(path)
    if lower.endswith(".json"):
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return json.dumps(json.load(handle), ensure_ascii=False, indent=1)
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def _text_docx(path: str) -> str:
    from docx import Document

    document = Document(path)
    chunks = [p.text for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            chunks.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(chunks)


def _text_xlsx(path: str) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(path, data_only=True, read_only=True)
    chunks = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            values = [str(v).strip() for v in row if v not in (None, "")]
            if values:
                chunks.append(" | ".join(values))
    return "\n".join(chunks)


def _text_pdf(path: str) -> str:
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n".join((page.extract_text() or "") for page in reader.pages)


# --------------------------------------------------------------------------
# Qidiruv
# --------------------------------------------------------------------------

def find_candidates(docs_dir: str) -> list[str]:
    """Ishonchnomaga o'xshash fayllarni yangisidan eskisiga qarab qaytaradi."""
    found: list[tuple[int, float, str]] = []
    for root, _dirs, files in os.walk(docs_dir):
        for name in files:
            if name.startswith("~$") or not name.lower().endswith(DOC_EXTENSIONS):
                continue
            path = os.path.join(root, name)
            haystack = (name + " " + root).lower()
            score = 1 if any(hint in haystack for hint in NAME_HINTS) else 0
            found.append((score, os.path.getmtime(path), path))
    found.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [path for _score, _mtime, path in found]


def find_last_poa(docs_dir: str) -> tuple[str | None, list[str]]:
    """Nomida yoki matnida ishonchnoma belgisi bor eng oxirgi faylni topadi."""
    notes: list[str] = []
    if not os.path.isdir(docs_dir):
        return None, [f"Papka topilmadi: {docs_dir}"]

    candidates = find_candidates(docs_dir)
    if not candidates:
        return None, [f"{docs_dir} ichida hujjat fayllari topilmadi."]

    named = [p for p in candidates
             if any(hint in os.path.basename(p).lower() for hint in NAME_HINTS)]
    if named:
        notes.append(f"Nomi bo'yicha {len(named)} ta nomzod topildi.")
        return named[0], notes

    for path in candidates[:40]:
        try:
            text = extract_text(path).lower()
        except Exception:
            continue
        if any(hint in text for hint in NAME_HINTS):
            notes.append("Fayl nomida emas, matn ichidan topildi.")
            return path, notes

    notes.append("Ishonchnoma aniqlanmadi, eng oxirgi o'zgartirilgan fayl olindi.")
    return candidates[0], notes


# --------------------------------------------------------------------------
# Maydonlarni ajratish
# --------------------------------------------------------------------------

PASSPORT_RE = re.compile(r"\b([A-Z]{2})\s*[-–—]?\s*(\d{7})\b")
PINFL_RE = re.compile(r"(?<!\d)(\d{14})(?!\d)")
NUMBER_RE = re.compile(r"(?:№|N|#|raqam|номер)\s*[:\-]?\s*([0-9]{1,6})", re.IGNORECASE)

FIO_LABELS = ("f.i.sh", "fish", "f.i.o", "ф.и.о", "фио", "ishonchli shaxs",
              "doverennoe", "доверенное лицо", "berildi", "выдана")
POSITION_LABELS = ("lavozim", "должность", "лавозим", "position")
PASSPORT_LABELS = ("pasport", "паспорт", "passport", "seriya", "серия", "id karta")

FIO_WORD_RE = re.compile(r"[A-Za-zЎўҚқҒғҲҳА-Яа-яЁё'`’]{3,}")


def _value_after_label(line: str, labels: tuple[str, ...]) -> str:
    low = line.lower()
    for label in labels:
        pos = low.find(label)
        if pos == -1:
            continue
        tail = line[pos + len(label):]
        # "Lavozimi:" kabi qo'shimchali yozuvlarda ajratgichgacha bo'lgan
        # qismni (masalan "i") tashlab yuboramiz
        separator = min((tail.find(ch) for ch in ":–—" if 0 <= tail.find(ch) <= 12),
                        default=-1)
        if separator >= 0:
            tail = tail[separator + 1:]
        tail = tail.lstrip(" \t:;-–—|.")
        tail = tail.split("|")[0].strip()
        if tail:
            return tail
    return ""


def _looks_like_fio(value: str) -> bool:
    words = FIO_WORD_RE.findall(value)
    return 2 <= len(words) <= 5 and len(value) <= 90


def parse_trusted_person(text: str, source_file: str = "") -> TrustedPerson:
    person = TrustedPerson(source_file=source_file)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for index, line in enumerate(lines):
        low = line.lower()

        if not person.fio and any(label in low for label in FIO_LABELS):
            value = _value_after_label(line, FIO_LABELS)
            if not _looks_like_fio(value) and index + 1 < len(lines):
                value = lines[index + 1].split("|")[0].strip()
            if _looks_like_fio(value):
                person.fio = value
                person.context.append(line)

        if not person.position and any(label in low for label in POSITION_LABELS):
            value = _value_after_label(line, POSITION_LABELS)
            if not value and index + 1 < len(lines):
                value = lines[index + 1].split("|")[0].strip()
            if value and len(value) <= 90:
                person.position = value
                person.context.append(line)

        if not person.passport and any(label in low for label in PASSPORT_LABELS):
            match = PASSPORT_RE.search(line)
            if not match and index + 1 < len(lines):
                match = PASSPORT_RE.search(lines[index + 1])
            if match:
                person.passport = f"{match.group(1)} {match.group(2)}"
                person.context.append(line)

    if not person.passport:
        match = PASSPORT_RE.search(text)
        if match:
            person.passport = f"{match.group(1)} {match.group(2)}"

    pinfl = PINFL_RE.search(text)
    if pinfl:
        person.pinfl = pinfl.group(1)

    person.doc_number = _last_document_number(text, source_file)
    return person


def _last_document_number(text: str, source_file: str) -> str:
    numbers = [int(m) for m in NUMBER_RE.findall(text) if m.isdigit()]
    from_name = NUMBER_RE.findall(os.path.basename(source_file))
    numbers.extend(int(m) for m in from_name if m.isdigit())
    plausible = [n for n in numbers if 0 < n < 100000]
    return str(max(plausible)) if plausible else ""


def next_number(previous: str) -> str:
    try:
        return str(int(previous) + 1)
    except (TypeError, ValueError):
        return ""


def read_last_poa(docs_dir: str) -> tuple[TrustedPerson | None, list[str]]:
    path, notes = find_last_poa(docs_dir)
    if path is None:
        return None, notes
    notes.append(f"Manba hujjat: {path}")
    try:
        text = extract_text(path)
    except Exception as exc:
        notes.append(f"Faylni o'qib bo'lmadi: {exc}")
        return None, notes
    person = parse_trusted_person(text, path)
    if person.missing():
        notes.append("Avtomatik topilmagan maydonlar: " + ", ".join(person.missing()))
    return person, notes
