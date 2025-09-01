from dataclasses import dataclass, field
from typing import Dict, Optional, Any


@dataclass
class FieldValue:
    name: str
    value: Optional[str]
    confidence: float
    source: str = "text"  # "text" or "ocr"
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    fields: Dict[str, FieldValue]
    text_digest: Optional[str] = None
    doc_meta: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str) -> Optional[FieldValue]:
        return self.fields.get(key)

    def merge_with(self, other: "ExtractionResult") -> "ExtractionResult":
        merged = dict(self.fields)
        for k, v in other.fields.items():
            if k not in merged:
                merged[k] = v
            else:
                # Weighted by confidence; prefer higher confidence
                if v.confidence > merged[k].confidence:
                    merged[k] = v
        meta = dict(self.doc_meta)
        meta.update(other.doc_meta)
        return ExtractionResult(fields=merged, text_digest=self.text_digest or other.text_digest, doc_meta=meta)


def aggregate_confidence(result: ExtractionResult) -> float:
    if not result.fields:
        return 0.0
    total = 0.0
    n = 0
    for fv in result.fields.values():
        if fv.value is None:
            continue
        total += max(0.0, min(1.0, fv.confidence))
        n += 1
    return total / n if n else 0.0

