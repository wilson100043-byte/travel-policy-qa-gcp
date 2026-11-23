"""Read self-authored Markdown policies and split them on level-two headings."""

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional


HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    id: str
    document: str
    section: str
    text: str
    effective_from: str
    effective_to: str

    def is_current(self, today: date) -> bool:
        return date.fromisoformat(self.effective_from) <= today and (
            not self.effective_to or today <= date.fromisoformat(self.effective_to)
        )


def _parse_frontmatter(raw: str) -> tuple:
    if not raw.startswith("---\n"):
        raise ValueError("document must start with YAML-style frontmatter")
    end = raw.find("\n---", 4)
    if end < 0:
        raise ValueError("frontmatter closing --- is missing")
    meta = {}
    for line in raw[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError("frontmatter contains an invalid line")
        meta[key.strip().lower()] = value.strip().strip('"\'')
    return meta, raw[end + 4 :].strip()


def parse_document(raw: str, filename: str) -> List[Chunk]:
    meta, body = _parse_frontmatter(raw.replace("\r\n", "\n").lstrip("\ufeff"))
    title = meta.get("title", "").strip()
    start = meta.get("effective_from", "").strip()
    end = meta.get("effective_to", "").strip()
    if not title or not start:
        raise ValueError("title and effective_from are required")
    try:
        start_date = date.fromisoformat(start)
        if end and date.fromisoformat(end) < start_date:
            raise ValueError("effective_to precedes effective_from")
    except ValueError as error:
        raise ValueError("invalid effective date in {}: {}".format(filename, error)) from error
    matches = list(HEADING.finditer(body))
    if not matches:
        raise ValueError("{} has no ## sections".format(filename))
    chunks = []
    for number, match in enumerate(matches):
        finish = matches[number + 1].start() if number + 1 < len(matches) else len(body)
        section = match.group(1).strip()
        content = body[match.end() : finish].strip()
        content = re.sub(r"[ \t]+", " ", content)
        content = re.sub(r"\n{3,}", "\n\n", content)
        if not content:
            continue
        identity = hashlib.sha256((filename + "\x00" + section).encode("utf-8")).hexdigest()[:16]
        chunks.append(Chunk(identity, title, section, content, start, end))
    if not chunks:
        raise ValueError("{} has no nonempty ## sections".format(filename))
    return chunks


def load_local_documents(directory: Path) -> List[Chunk]:
    if not directory.is_dir():
        raise FileNotFoundError("policy document directory not found: {}".format(directory))
    files = sorted(directory.glob("*.md"))
    if not files:
        raise FileNotFoundError("no Markdown policy documents found in {}".format(directory))
    chunks = []
    for path in files:
        chunks.extend(parse_document(path.read_text(encoding="utf-8"), path.name))
    return chunks


def fingerprint_documents(directory: Path) -> Optional[str]:
    if not directory.is_dir():
        return None
    paths = sorted(directory.glob("*.md"))
    if not paths:
        return None
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
    return digest.hexdigest()
