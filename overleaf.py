"""Patch a professional summary in LaTeX without reformatting the CV."""

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from stat import S_ISLNK
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from documents import MAX_FILE_BYTES

SECTION = re.compile(r"(?m)^[ \t]*\\(?:section\*?|cvsection)\s*\{([^{}\r\n]+)\}[^\S\r\n]*(?:%[^\r\n]*)?(?:\r?\n|\Z)")
END = re.compile(r"(?m)^[ \t]*\\end\{document\}")
HEADINGS = {"professional summary", "summary", "professional profile", "career profile", "profile", "personal statement"}
WRAPPER = re.compile(
    r"(?:[{}]+|\\(?:small|footnotesize|normalsize|noindent|raggedright|justifying)[ \t]*\{?|"
    r"\\(?:begin|end)\{(?:itemize|enumerate|description|quote|flushleft|samepage)\}(?:\[[^\r\n]*\])?|"
    r"\\item(?:\[[^\r\n]*\])?[ \t]*\{?|\\vspace\*?\{[^{}\r\n]*\})\s*"
)
INLINE_PREFIX = re.compile(r"\\(?:item|noindent)[ \t]+")
TEX_SPECIAL = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "#": r"\#", "$": r"\$",
               "%": r"\%", "&": r"\&", "_": r"\_", "^": r"\textasciicircum{}", "~": r"\textasciitilde{}"}
PLAIN = re.compile(r"(?:[^\\{}%$#&_^~]|\\[&#%_$])+\Z")
MAX_ARCHIVE_SIZE = 45 * 1024 * 1024
MAX_ARCHIVE_FILES = 300


@dataclass(frozen=True)
class SummarySpan:
    start: int
    end: int
    original: str


def summary_span(source: str) -> SummarySpan:
    sections = list(SECTION.finditer(source))
    summaries = [index for index, match in enumerate(sections) if " ".join(match[1].lower().split()) in HEADINGS]
    if len(summaries) != 1:
        raise ValueError("Choose a .tex file with a single Professional Summary or Profile section.")
    index = summaries[0]
    start = sections[index].end()
    closing = END.search(source, start)
    boundaries = [sections[index + 1].start()] if index + 1 < len(sections) else []
    if closing:
        boundaries.append(closing.start())
    if not boundaries:
        raise ValueError("The end of the Professional Summary section could not be identified safely.")

    lines: list[tuple[int, int]] = []
    position = start
    for raw in source[start:min(boundaries)].splitlines(keepends=True):
        line = raw.strip()
        if line and not line.startswith("%") and not WRAPPER.fullmatch(line):
            line_start = position + len(raw) - len(raw.lstrip())
            prefix = INLINE_PREFIX.match(line)
            if prefix:
                if lines:
                    raise ValueError("The summary has multiple items. Edit it directly in Overleaf to preserve its structure.")
                line_start += prefix.end()
                line = line[prefix.end():]
            if not PLAIN.fullmatch(line):
                raise ValueError("The summary uses inline LaTeX formatting. Edit it directly in Overleaf to preserve those commands.")
            lines.append((line_start, position + len(raw.rstrip())))
        position += len(raw)
    if not lines:
        raise ValueError("The Professional Summary section has no editable paragraph.")
    for previous, current in zip(lines, lines[1:]):
        gap = source[previous[1]:current[0]]
        if gap.strip() or gap.count("\n") != 1:
            raise ValueError("The summary is split into multiple blocks. Edit it directly in Overleaf to keep its layout.")
    first, last = lines[0][0], lines[-1][1]
    return SummarySpan(first, last, " ".join(source[first:last].split()))


def decode_source(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Export the LaTeX file with UTF-8 encoding.") from error


def replace_summary(data: bytes, summary: str) -> bytes:
    source = decode_source(data)
    span = summary_span(source)
    clean = " ".join(summary.split())
    if not clean:
        raise ValueError("Add an approved summary before exporting.")
    escaped = "".join(TEX_SPECIAL.get(char, char) for char in clean)
    return (source[:span.start] + escaped + source[span.end:]).encode("utf-8")


def archive_members(archive: ZipFile):
    entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_FILES or sum(item.file_size for item in entries) > MAX_ARCHIVE_SIZE:
        raise ValueError("The Overleaf ZIP is too large for this CV workflow.")
    names = set()
    for item in entries:
        path = PurePosixPath(item.filename)
        if (not path.parts or path.is_absolute() or ".." in path.parts or "\\" in item.filename
                or ":" in path.parts[0] or item.filename in names or S_ISLNK(item.external_attr >> 16)
                or item.flag_bits & 1):
            raise ValueError("Use a standard source ZIP exported from Overleaf, without links or encrypted files.")
        names.add(item.filename)
    return entries


def available_sources(filename: str, data: bytes) -> dict[str, SummarySpan]:
    if not 0 < len(data) <= MAX_FILE_BYTES:
        raise ValueError("Choose an Overleaf source file up to 15 MiB.")
    if filename.lower().endswith(".tex"):
        return {filename: summary_span(decode_source(data))}
    if not filename.lower().endswith(".zip"):
        raise ValueError("Upload the .tex file or the Overleaf source ZIP.")
    try:
        with ZipFile(BytesIO(data)) as archive:
            targets = {}
            for item in archive_members(archive):
                if item.filename.lower().endswith(".tex"):
                    try:
                        targets[item.filename] = summary_span(decode_source(archive.read(item)))
                    except ValueError:
                        continue
            if not targets:
                raise ValueError("No safely editable Professional Summary was found in the ZIP. Try the individual .tex file to see why.")
            return targets
    except (BadZipFile, NotImplementedError) as error:
        raise ValueError("This file is not a readable Overleaf source ZIP.") from error


def export_overleaf(filename: str, data: bytes, target: str, summary: str) -> bytes:
    if filename.lower().endswith(".tex"):
        return replace_summary(data, summary)
    output = BytesIO()
    try:
        with ZipFile(BytesIO(data)) as original, ZipFile(output, mode="w", compression=ZIP_DEFLATED) as updated:
            entries = archive_members(original)
            if target not in {item.filename for item in entries if item.filename.lower().endswith(".tex")}:
                raise ValueError("Choose the .tex file that holds your Professional Summary.")
            for item in entries:
                contents = original.read(item)
                updated.writestr(item, replace_summary(contents, summary) if item.filename == target else contents)
            updated.comment = original.comment
    except (BadZipFile, NotImplementedError) as error:
        raise ValueError("The ZIP could not be copied. Download a new source ZIP from Overleaf.") from error
    return output.getvalue()
