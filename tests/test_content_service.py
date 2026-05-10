import unittest
from unittest.mock import patch

from src.services.content_service import GeminiContentService


class GeminiContentServiceJsonParsingTests(unittest.TestCase):
    def make_service(self) -> GeminiContentService:
        with patch("google.generativeai.GenerativeModel"):
            return GeminiContentService(api_key=None, model_name="test-model")

    def test_parse_json_uses_first_valid_json_object_when_extra_data_follows(self):
        service = self.make_service()
        text = '{"candidates": [{"hook": "You are hiding."}]}\n{"extra": true}'

        data = service._parse_json(text)

        self.assertEqual(data["candidates"][0]["hook"], "You are hiding.")

    def test_parse_json_extracts_json_object_from_surrounding_text(self):
        service = self.make_service()
        text = 'Here is the JSON:\n{"hook": "Your comfort is loud."}\nDone.'

        data = service._parse_json(text)

        self.assertEqual(data["hook"], "Your comfort is loud.")


if __name__ == "__main__":
    unittest.main()
