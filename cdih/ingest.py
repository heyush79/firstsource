"""Document ingestion: turn an uploaded file (or pasted text) into Gemini parts.

Strategy
--------
- Plain text / markdown  -> sent as text.
- PDF                    -> try local text extraction first (pypdf). If the PDF
                            is digital and yields real text, send that text
                            (cheaper + faster). If it looks scanned (little or
                            no extractable text), fall back to sending the raw
                            PDF bytes so Gemini's vision reads it directly.
- Images (png/jpg/webp)  -> sent as image bytes; Gemini vision does the OCR.
"""

from dataclasses import dataclass
from io import BytesIO

from google.genai import types
from pypdf import PdfReader

TEXT_EXTENSIONS = {"txt", "md", "text"}
IMAGE_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}

# Below this many characters per page we assume the PDF is a scan.
MIN_CHARS_PER_PAGE = 120


@dataclass
class IngestedDocument:
    """A document prepared for the LLM, plus metadata for the UI."""

    parts: list  # list of google.genai types.Part / str
    source_name: str
    ingest_mode: str  # "text", "pdf-text", "pdf-vision", "image-vision"
    preview_text: str  # short preview shown in the UI


def from_text(text: str, source_name: str = "pasted text") -> IngestedDocument:
    return IngestedDocument(
        parts=[text],
        source_name=source_name,
        ingest_mode="text",
        preview_text=text[:1500],
    )


def from_file(filename: str, data: bytes) -> IngestedDocument:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext in TEXT_EXTENSIONS:
        return from_text(data.decode("utf-8", errors="replace"), filename)

    if ext == "pdf":
        text = _extract_pdf_text(data)
        pages = max(_pdf_page_count(data), 1)
        if len(text.strip()) >= MIN_CHARS_PER_PAGE * pages:
            return IngestedDocument(
                parts=[text],
                source_name=filename,
                ingest_mode="pdf-text",
                preview_text=text[:1500],
            )
        # Scanned or image-only PDF: let the model read it visually.
        return IngestedDocument(
            parts=[types.Part.from_bytes(data=data, mime_type="application/pdf")],
            source_name=filename,
            ingest_mode="pdf-vision",
            preview_text="(scanned PDF — sent to the model as an image document)",
        )

    if ext in IMAGE_MIME:
        return IngestedDocument(
            parts=[types.Part.from_bytes(data=data, mime_type=IMAGE_MIME[ext])],
            source_name=filename,
            ingest_mode="image-vision",
            preview_text="(image document — sent to the model for visual reading)",
        )

    raise ValueError(
        f"Unsupported file type '.{ext}'. Supported: .txt, .md, .pdf, .png, .jpg, .jpeg, .webp"
    )


def _extract_pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _pdf_page_count(data: bytes) -> int:
    try:
        return len(PdfReader(BytesIO(data)).pages)
    except Exception:
        return 1
