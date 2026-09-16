"""Text extraction, normalisation and chunking."""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from dataclasses import dataclass

from app.core.errors import ValidationError
from app.providers.base import estimate_tokens

_WS_RE = re.compile(r"[ \t ]+")
_NEWLINES_RE = re.compile(r"\n{3,}")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class ExtractedText:
    text: str
    page_count: int
    warnings: list[str]


@dataclass(slots=True)
class Chunk:
    ordinal: int
    content: str
    page: int | None
    token_estimate: int


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _NEWLINES_RE.sub("\n\n", text)
    return text.strip()


def extract_text(data: bytes, filename: str, content_type: str) -> ExtractedText:
    """Extract plain text from the supported upload formats."""
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    warnings: list[str] = []

    if suffix == ".pdf" or content_type == "application/pdf":
        return _extract_pdf(data)

    if suffix == ".docx" or content_type.endswith("wordprocessingml.document"):
        return _extract_docx(data)

    decoded = data.decode("utf-8", errors="replace")
    if "�" in decoded:
        warnings.append("Some bytes were not valid UTF-8 and were replaced.")

    if suffix == ".json":
        try:
            parsed = json.loads(decoded)
            decoded = json.dumps(parsed, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as exc:
            raise ValidationError(f"Invalid JSON document: {exc.msg}") from exc

    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        rows = list(csv.reader(io.StringIO(decoded), delimiter=delimiter))
        if rows:
            header, *body = rows
            lines = [", ".join(header)]
            lines += [
                "; ".join(f"{h}: {v}" for h, v in zip(header, row, strict=False) if v)
                for row in body
            ]
            decoded = "\n".join(lines)

    return ExtractedText(text=normalise(decoded), page_count=1, warnings=warnings)


def _extract_pdf(data: bytes) -> ExtractedText:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ValidationError("pypdf is required to ingest PDF documents.") from exc

    warnings: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ValidationError(f"Could not read PDF: {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ValidationError("Encrypted PDFs are not supported.") from exc

    pages: list[str] = []
    for index, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
            warnings.append(f"Page {index + 1} could not be parsed.")

    text = "\n\n".join(f"[[page:{i + 1}]]\n{p}" for i, p in enumerate(pages) if p.strip())
    if not text.strip():
        warnings.append(
            "No embedded text found. This is likely a scanned PDF; OCR is required "
            "(see the OCR integration point in DocumentService)."
        )
    return ExtractedText(text=normalise(text), page_count=len(reader.pages), warnings=warnings)


def _extract_docx(data: bytes) -> ExtractedText:
    """DOCX is a zip of XML; read the document body without extra dependencies."""
    import xml.etree.ElementTree as ET
    import zipfile

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValidationError("Could not read DOCX document.") from exc

    root = ET.fromstring(xml)
    paragraphs = []
    for para in root.iter(f"{{{ns['w']}}}p"):
        text = "".join(node.text or "" for node in para.iter(f"{{{ns['w']}}}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return ExtractedText(text=normalise("\n\n".join(paragraphs)), page_count=1, warnings=[])


_PAGE_MARKER = re.compile(r"\[\[page:(\d+)\]\]")


def chunk_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    """Sentence-aware sliding window chunker that tracks page markers."""
    if chunk_size <= 0:
        raise ValidationError("chunk_size must be greater than zero.")
    if chunk_overlap >= chunk_size:
        raise ValidationError("chunk_overlap must be smaller than chunk_size.")

    text = text.strip()
    if not text:
        return []

    # Record page boundaries, then strip the markers from the indexed content.
    page_at: list[tuple[int, int]] = []
    cleaned_parts: list[str] = []
    cursor = 0
    offset = 0
    for match in _PAGE_MARKER.finditer(text):
        cleaned_parts.append(text[cursor : match.start()])
        offset += match.start() - cursor
        page_at.append((offset, int(match.group(1))))
        cursor = match.end()
    cleaned_parts.append(text[cursor:])
    cleaned = "".join(cleaned_parts).strip()

    def page_for(position: int) -> int | None:
        page = None
        for start, number in page_at:
            if start <= position:
                page = number
            else:
                break
        return page

    sentences = [s for s in _SENTENCE_END.split(cleaned) if s.strip()]
    chunks: list[Chunk] = []
    buffer: list[str] = []
    buffer_len = 0
    position = 0
    chunk_start = 0

    def flush() -> None:
        nonlocal buffer, buffer_len, chunk_start
        if not buffer:
            return
        content = " ".join(buffer).strip()
        if content:
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    content=content,
                    page=page_for(chunk_start),
                    token_estimate=estimate_tokens(content),
                )
            )
        buffer = []
        buffer_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not buffer:
            chunk_start = position
        # A single oversized sentence is hard-split so nothing is dropped.
        if len(sentence) > chunk_size:
            flush()
            for start in range(0, len(sentence), chunk_size - chunk_overlap):
                piece = sentence[start : start + chunk_size].strip()
                if piece:
                    chunks.append(
                        Chunk(
                            ordinal=len(chunks),
                            content=piece,
                            page=page_for(position + start),
                            token_estimate=estimate_tokens(piece),
                        )
                    )
            position += len(sentence) + 1
            continue

        if buffer_len + len(sentence) + 1 > chunk_size:
            flush()
            # Rebuild the overlap tail from the end of the previous chunk.
            if chunk_overlap and chunks:
                tail = chunks[-1].content[-chunk_overlap:]
                buffer = [tail]
                buffer_len = len(tail)
                chunk_start = max(0, position - chunk_overlap)
            else:
                chunk_start = position

        buffer.append(sentence)
        buffer_len += len(sentence) + 1
        position += len(sentence) + 1

    flush()
    return chunks
