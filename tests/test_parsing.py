import json
import unittest

from src.axa_extractor.extractors.text_pdf import TextPDFExtractor
from src.axa_extractor.fields import aggregate_confidence, ExtractionResult, FieldValue
from src.axa_extractor.storage import Storage


class TestParsing(unittest.TestCase):
    def setUp(self):
        self.extractor = TextPDFExtractor()
        # Fake text content simulating PDF extraction
        self.sample_text = (
            "AXA XL Claim Form\n"
            "Customer Name: Jane Doe\n"
            "Address: 123 Main St, Springfield\n"
            "Policy Number: ABC-123456\n"
            "Claim Type: Property Damage\n"
            "Date of Incident: 2024-05-01\n"
            "Claim Amount: $1,234.56\n"
            "Agent: John Smith\n"
            "Submission Date: 2024-05-03\n"
        )

    def test_scoring(self):
        # Directly test the scoring heuristics
        self.assertGreaterEqual(self.extractor._score("policy_number", "ABC-123456"), 0.8)
        self.assertGreaterEqual(self.extractor._score("claim_amount", "$123.00"), 0.8)
        self.assertGreater(self.extractor._score("customer_name", "Jane Doe"), 0.5)

    def test_aggregate_confidence(self):
        result = ExtractionResult(fields={
            "policy_number": FieldValue("policy_number", "ABC-123", 0.9),
            "customer_name": FieldValue("customer_name", "Jane Doe", 0.8),
            "address": FieldValue("address", None, 0.0),
        })
        avg = aggregate_confidence(result)
        self.assertAlmostEqual(avg, (0.9 + 0.8) / 2)

    def test_storage_roundtrip(self):
        storage = Storage(db_path=":memory:")
        result = {
            "fields": {
                "policy_number": {"value": "ABC-123456", "confidence": 0.9, "source": "text"},
                "submission_date": {"value": "2024-05-03", "confidence": 0.8, "source": "text"},
                "form_type": {"value": "AXA XL Claim Form", "confidence": 0.6, "source": "text"}
            },
            "confidence": 0.8,
            "meta": {}
        }
        doc_id = storage.save_extraction("sample.pdf", result)
        self.assertIsInstance(doc_id, int)
        doc = storage.get_document(doc_id)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["filename"], "sample.pdf")
        names = {f["name"] for f in doc["fields"]}
        self.assertIn("policy_number", names)


if __name__ == "__main__":
    unittest.main()

