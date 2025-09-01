from typing import List, Optional, Dict, Any

from .fields import ExtractionResult, aggregate_confidence
from .extractors.base import BaseExtractor
from .extractors.text_pdf import TextPDFExtractor
from .extractors.ocr_pdf import OCRPDFExtractor


class ExtractionPipeline:
    def __init__(self, extractors: Optional[List[BaseExtractor]] = None) -> None:
        self.extractors = extractors or [TextPDFExtractor(), OCRPDFExtractor()]

    def run(self, file_bytes: bytes, config: Optional[dict] = None) -> Dict[str, Any]:
        results: List[ExtractionResult] = []
        for extractor in self.extractors:
            try:
                if extractor.can_process(file_bytes):
                    res = extractor.extract(file_bytes, config=config)
                    results.append(res)
            except Exception as e:
                # Continue with other extractors
                results.append(ExtractionResult(fields={}, doc_meta={"error": str(e), "extractor": extractor.__class__.__name__}))

        if not results:
            return {"fields": {}, "confidence": 0.0, "meta": {"error": "No extractor available"}}

        merged = results[0]
        for r in results[1:]:
            merged = merged.merge_with(r)

        conf = aggregate_confidence(merged)
        return {"fields": {k: v.__dict__ for k, v in merged.fields.items()}, "confidence": conf, "meta": merged.doc_meta}

