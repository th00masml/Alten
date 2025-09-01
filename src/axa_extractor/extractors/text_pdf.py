import io
import re
from typing import Optional, Dict, Any, List, Tuple

from ..fields import FieldValue, ExtractionResult
from .base import BaseExtractor


DEFAULT_PATTERNS = {
    "customer_name": [
        r"(?:Insured|Insured\s+Name|Name\s+of\s+Insured|Customer\s+Name|Policy\s+Holder)\s*[:#\-]?\s*([A-Z][A-Za-z ,.'\-]{2,}(?:\s+[A-Z][A-Za-z ,.'\-]{1,})?)",
        r"(?:Name)\s*[:#\-]?\s*([A-Z][A-Za-z ,.'\-]{2,}(?:\s+[A-Z][A-Za-z ,.'\-]{1,})?)",
    ],
    "address": [
        # Capture up to 2 lines for addresses; stop at next label-like token
        r"Address\s*[:#\-]?\s*([\s\S]{5,160}?)\n(?=\S+\s*[:#\-])",
        r"Address\s*[:#\-]?\s*([\s\S]{5,120})",
    ],
    "policy_number": [
        r"Policy\s*(?:No\.?|Number|#)?\s*[:#\-]?\s*([A-Z0-9][A-Z0-9\-/]{4,})",
    ],
    "claim_type": [
        r"Claim\s*Type\s*[:#\-]?\s*([A-Za-z /]{3,80})",
        r"Type\s*of\s*Claim\s*[:#\-]?\s*([A-Za-z /]{3,80})",
    ],
    "date_of_incident": [
        r"(?:Date\s*of\s*Incident|Loss\s*Date|Date\s*of\s*Loss)\s*[:#\-]?\s*(\d{2,4}[-/.]\d{1,2}[-/.]\d{1,2})",
    ],
    "claim_amount": [
        r"(?:Claim\s*Amount|Amount\s*Claimed|Total\s*Claim(?:ed)?|Amount)\s*[:#\-]?\s*([$€£]?\s?[\d,.]+(?:\.\d{2})?)",
    ],
    "agent": [
        r"(?:Agent|Broker|Branch|Producer)\s*[:#\-]?\s*([A-Za-z0-9 .,'&\-]{3,120})",
    ],
    "form_type": [
        r"(AXA\s*XL[\s\S]{0,40}?(?:Claim|Form|Policy|Customer|Schedule|Certificate))",
    ],
    "submission_date": [
        r"(?:Submission\s*Date|Date\s*Submitted|Issue\s*Date|Submission)\s*[:#\-]?\s*(\d{2,4}[-/.]\d{1,2}[-/.]\d{1,2})",
    ],
}


class TextPDFExtractor(BaseExtractor):
    name = "text"

    def can_process(self, file_bytes: bytes) -> bool:
        # Try to read some text from any available engine
        try:
            text, _ = self._extract_text_any(file_bytes)
            return bool(text.strip())
        except Exception:
            return False

    def extract(self, file_bytes: bytes, config: Optional[dict] = None) -> ExtractionResult:
        cfg_patterns: Dict[str, Any] = (config or {}).get("patterns", {})
        # Merge default patterns with config-provided ones to broaden coverage
        patterns: Dict[str, List[str]] = {}
        keys = set(DEFAULT_PATTERNS.keys()) | set(cfg_patterns.keys())
        for k in keys:
            merged = []
            if k in DEFAULT_PATTERNS:
                merged.extend(DEFAULT_PATTERNS[k])
            if k in cfg_patterns:
                merged.extend(cfg_patterns[k])
            # de-duplicate while preserving order
            seen = set()
            uniq = []
            for p in merged:
                if p not in seen:
                    uniq.append(p)
                    seen.add(p)
            patterns[k] = uniq
        full_text, meta = self._extract_text_any(file_bytes)
        norm_text = self._normalize_text(full_text)

        fields: Dict[str, FieldValue] = {}

        # Pass 1: regex-based search (robust to newlines)
        for field, pats in patterns.items():
            best_val = None
            best_conf = 0.0
            multi_hits = 0
            for pat in pats:
                try:
                    m = re.search(pat, norm_text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
                except re.error:
                    continue
                if m:
                    multi_hits += 1
                    candidate = m.group(1).strip()
                    conf = self._score(field, candidate)
                    if conf > best_conf:
                        best_conf = conf
                        best_val = candidate
            if best_val is not None:
                if multi_hits > 1 and best_conf > 0.2:
                    best_conf -= 0.05
                fields[field] = FieldValue(name=field, value=best_val, confidence=max(0.0, min(1.0, best_conf)), source=self.name)
            else:
                fields[field] = FieldValue(name=field, value=None, confidence=0.0, source=self.name)

        # Pass 2: label-based key→value scanning across lines
        kv_overrides = self._kv_scan(full_text)
        for k, (val, conf) in kv_overrides.items():
            cur = fields.get(k)
            if val and (cur is None or (cur.value is None or conf > cur.confidence)):
                fields[k] = FieldValue(name=k, value=val, confidence=conf, source=self.name, meta={"method": "kv"})

        doc_meta = {
            **meta,
            "contains_axa_xl": bool(re.search(r"AXA\s*XL", full_text, flags=re.IGNORECASE)),
        }

        return ExtractionResult(fields=fields, text_digest=str(hash(full_text)), doc_meta=doc_meta)

    def _score(self, field: str, value: str) -> float:
        v = value.strip()
        if not v:
            return 0.0
        if field == "policy_number":
            conf = 0.6
            if re.fullmatch(r"[A-Z0-9\-/]{6,}", v):
                conf = 0.9
            return conf
        if field in ("date_of_incident", "submission_date"):
            if re.fullmatch(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", v) or re.fullmatch(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", v):
                return 0.85
            return 0.5
        if field == "claim_amount":
            if re.fullmatch(r"[$€£]?\s?[\d,.]+(\.\d{2})?", v):
                return 0.85
            return 0.5
        if field == "customer_name":
            if len(v.split()) >= 2 and all(len(p) >= 2 for p in v.split()[:2]):
                return 0.8
            return 0.5
        if field == "address":
            if re.search(r"\d", v) and re.search(r"(St|Street|Ave|Avenue|Rd|Road|Blvd|Lane|Ln|Drive|Dr|Ct|Court)\b", v, re.IGNORECASE):
                return 0.75
            return 0.5
        if field in ("agent", "claim_type", "form_type"):
            return 0.6 if len(v) >= 3 else 0.4
        return 0.5

    def _extract_text_any(self, file_bytes: bytes) -> Tuple[str, Dict[str, Any]]:
        """Extract text using pdfplumber if available; fallback to PyPDF2."""
        meta: Dict[str, Any] = {"engine": None, "num_pages": 0}
        # Try pdfplumber for better layout
        try:
            import pdfplumber  # type: ignore
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                pages_text: List[str] = []
                for page in pdf.pages:
                    try:
                        t = page.extract_text(x_tolerance=1, y_tolerance=1) or ""
                    except Exception:
                        t = ""
                    pages_text.append(t)
                text = "\n".join(pages_text)
                meta.update({"engine": "pdfplumber", "num_pages": len(pdf.pages)})
                if text.strip():
                    return text, meta
        except Exception:
            pass

        # Fallback to PyPDF2
        try:
            from PyPDF2 import PdfReader  # lazy import
        except Exception as e:
            return "", {"error": f"PyPDF2 not available: {e}", **meta}
        reader = PdfReader(io.BytesIO(file_bytes))
        full_text_parts = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            full_text_parts.append(t)
        full_text = "\n".join(full_text_parts)
        meta.update({"engine": "pypdf2", "num_pages": len(reader.pages)})
        return full_text, meta

    def _normalize_text(self, text: str) -> str:
        # Normalize whitespace but preserve newlines for multi-line capture
        t = re.sub(r"\u00A0", " ", text)  # non-breaking space
        t = re.sub(r"-\n", "", t)  # join hyphenated line breaks
        t = re.sub(r"[\t\r]+", " ", t)
        t = re.sub(r"[ ]{2,}", " ", t)
        return t

    def _kv_scan(self, text: str) -> Dict[str, Tuple[Optional[str], float]]:
        """Key-value scanning across lines for common labels."""
        lines = [ln.strip() for ln in text.splitlines()]
        label_keywords = {
            "customer_name": ["insured", "insured name", "name of insured", "customer name", "policy holder", "name"],
            "address": ["address"],
            "policy_number": ["policy no", "policy number", "policy #", "policy"],
            "claim_type": ["claim type", "type of claim"],
            "date_of_incident": ["date of incident", "loss date", "date of loss"],
            "claim_amount": ["claim amount", "amount claimed", "total claim", "amount"],
            "agent": ["agent", "broker", "branch", "producer"],
            "submission_date": ["submission date", "date submitted", "issue date", "submission"],
            "form_type": ["axa xl", "form", "policy", "customer", "claim"],
        }

        results: Dict[str, Tuple[Optional[str], float]] = {}

        def is_label_line(s: str) -> bool:
            return bool(re.search(r"[:#\-]\s*$", s)) or (len(s.split()) <= 6 and s.endswith(":"))

        for idx, raw in enumerate(lines):
            low = raw.lower()
            for field, keys in label_keywords.items():
                if any(k in low for k in keys):
                    # Try same-line value first
                    parts = re.split(r"[:#\-]", raw, maxsplit=1)
                    value = None
                    if len(parts) > 1 and parts[1].strip():
                        value = parts[1].strip()
                    else:
                        # Next non-empty line that is not a label
                        j = idx + 1
                        while j < len(lines) and not lines[j].strip():
                            j += 1
                        if j < len(lines) and not is_label_line(lines[j]):
                            value = lines[j].strip()
                            # Address may span multiple lines
                            if field == "address" and j + 1 < len(lines) and lines[j + 1] and not is_label_line(lines[j + 1]):
                                value = (value + ", " + lines[j + 1].strip()).strip(", ")

                    if value:
                        value = re.sub(r"\s{2,}", " ", value).strip()
                        conf = min(1.0, self._score(field, value) + 0.1)
                        cur = results.get(field)
                        if cur is None or (conf > (cur[1] or 0.0)):
                            results[field] = (value, conf)
        return results
