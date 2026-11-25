"""Find supported files and produce excerpts with page and passage numbers."""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

from pypdf import PdfReader
from pypdf.errors import PyPdfError

SUPPORTED_TYPES = {".pdf", ".txt", ".md"}
MAX_FILE_BYTES = 15 * 1024 * 1024
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120


@dataclass(frozen=True)
class Corpus:
    root: Path
    files: tuple[Path, ...]
    fingerprint: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class Passage:
    filename: str
    page: int
    part: int
    text: str


def scan_folder(root: Path) -> Corpus:
    files, warnings = [], []
    fingerprint = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in SUPPORTED_TYPES:
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                warnings.append(f"Skipped {relative}. The file exceeds 15 MiB.")
                continue
            with path.open("rb") as handle:
                file_digest = hashlib.file_digest(handle, "sha256").digest()
        except OSError:
            warnings.append(f"Could not read {relative}.")
            continue
        files.append(path)
        fingerprint.update(relative.as_posix().encode() + b"\0" + file_digest)
    return Corpus(root, tuple(files), fingerprint.hexdigest()[:24], tuple(warnings))


def read_pages(path: Path) -> Iterator[tuple[int, str]]:
    if path.suffix.lower() != ".pdf":
        yield 0, path.read_text(encoding="utf-8-sig")
        return
    with path.open("rb") as handle:
        yield from read_pdf(handle)


def read_pdf(handle: BinaryIO) -> Iterator[tuple[int, str]]:
    reader = PdfReader(handle)
    if reader.is_encrypted:
        raise PyPdfError("Export an unlocked copy of the PDF.")
    for page_number, page in enumerate(reader.pages, start=1):
        yield page_number, page.extract_text() or ""


def chunk_text(text: str) -> Iterator[str]:
    """Split text into short overlapping windows, using word boundaries where possible."""
    text = re.sub(r"[^\S\n]+", " ", text).strip()
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = max(text.rfind(" ", start, end), text.rfind("\n", start, end))
            if boundary > start + CHUNK_SIZE // 2:
                end = boundary
        excerpt = text[start:end].strip()
        if excerpt:
            yield excerpt
        if end == len(text):
            break
        next_start = end - CHUNK_OVERLAP
        boundary = re.search(r"\s", text[next_start:end])
        start = next_start + (boundary.end() if boundary else 0)


def iter_passages(corpus: Corpus, warnings: list[str]) -> Iterator[Passage]:
    for path in corpus.files:
        filename = path.relative_to(corpus.root).as_posix()
        found_text = False
        try:
            for page, text in read_pages(path):
                for part, excerpt in enumerate(chunk_text(text), start=1):
                    found_text = True
                    yield Passage(filename, page, part, excerpt)
        except (OSError, ValueError, PyPdfError) as error:
            warnings.append(f"Could not fully read {filename}. {error}")
            continue
        if not found_text:
            warnings.append(f"No selectable text in {filename}. Try a local text export or OCR.")
