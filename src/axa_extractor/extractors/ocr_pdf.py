from typing import Optional, Dict

from ..fields import ExtractionResult, FieldValue
from .base import BaseExtractor


class OCRPDFExtractor(BaseExtractor):
    name = "ocr"

    def __init__(self) -> None:
        # Lazy import flags
        self.ready = False
        try:
            import pytesseract  # noqa: F401
            from PIL import Image  # noqa: F401
            # For rendering PDFs to images, attempt pymupdf first
            try:
                import fitz  # type: ignore # noqa: F401
                self.renderer = "pymupdf"
            except Exception:
                try:
                    import pdf2image  # type: ignore # noqa: F401
                    self.renderer = "pdf2image"
                except Exception:
                    self.renderer = None
            self.ready = self.renderer is not None
        except Exception:
            self.ready = False

    def can_process(self, file_bytes: bytes) -> bool:
        return self.ready

    def extract(self, file_bytes: bytes, config: Optional[dict] = None) -> ExtractionResult:
        # Minimal implementation: if not ready, return empty with signal
        if not self.ready:
            return ExtractionResult(fields={})

        # Render pages to images, run OCR, then reuse regex patterns from text extractor
        text = self._render_and_ocr(file_bytes)
        from .text_pdf import DEFAULT_PATTERNS
        patterns = (config or {}).get("patterns", DEFAULT_PATTERNS)
        fields: Dict[str, FieldValue] = {}

        import re
        for field, pats in patterns.items():
            value = None
            conf = 0.0
            for pat in pats:
                try:
                    m = re.search(pat, text, flags=re.IGNORECASE | re.MULTILINE)
                except re.error:
                    continue
                if m:
                    v = m.group(1).strip()
                    value = v
                    conf = max(conf, 0.6)  # baseline for OCR hits
            fields[field] = FieldValue(name=field, value=value, confidence=conf * 0.9, source=self.name)

        return ExtractionResult(fields=fields, text_digest=str(hash(text)), doc_meta={"ocr": True})

    def _render_and_ocr(self, file_bytes: bytes) -> str:
        import io
        import pytesseract
        from PIL import Image
        text_parts = []
        if self.renderer == "pymupdf":
            import fitz  # type: ignore
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    text_parts.append(pytesseract.image_to_string(img))
        elif self.renderer == "pdf2image":
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(file_bytes, dpi=200)
            for img in images:
                text_parts.append(pytesseract.image_to_string(img))
        return "\n".join(text_parts)

