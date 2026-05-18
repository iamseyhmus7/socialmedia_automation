import math
import sys
import types
import unittest


class FakeEmbedding:
    values = [3.0, 4.0]


class FakeResult:
    embeddings = [FakeEmbedding()]


class FakeModels:
    def __init__(self):
        self.call = None

    def embed_content(self, **kwargs):
        self.call = kwargs
        return FakeResult()


class FakeClient:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.models = FakeModels()


class FakeEmbedContentConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class ScriptEmbeddingServiceTests(unittest.TestCase):
    def setUp(self):
        fake_genai = types.SimpleNamespace(Client=FakeClient)
        fake_types = types.SimpleNamespace(EmbedContentConfig=FakeEmbedContentConfig)
        fake_generativeai = types.SimpleNamespace(GenerativeModel=lambda *args, **kwargs: None, configure=lambda **kwargs: None)
        google_module = types.SimpleNamespace(genai=fake_genai, generativeai=fake_generativeai)
        sys.modules["google"] = google_module
        sys.modules["google.genai"] = types.SimpleNamespace(types=fake_types)
        sys.modules["google.genai.types"] = fake_types
        sys.modules["google.generativeai"] = fake_generativeai

    def test_embedding_text_includes_script_and_media_context(self):
        from src.services.script_embedding_service import ScriptEmbeddingService

        service = ScriptEmbeddingService("key", "gemini-embedding-001", dimensions=2)
        text = service.embedding_text(
            {
                "script": {
                    "hook": "Your excuses are costing you.",
                    "body": "Delay trains comfort.",
                    "outro": "Choose pressure.",
                    "loop_ending": "Your excuses are costing you.",
                },
                "media_plan": {
                    "visual_direction": {"overall_theme": "discipline under pressure"},
                    "video_scenes": [{"search_query": "athlete training alone dark gym"}],
                },
            }
        )

        self.assertIn("Your excuses are costing you.", text)
        self.assertIn("discipline under pressure", text)
        self.assertIn("athlete training alone dark gym", text)

    def test_embed_script_requests_semantic_similarity_and_normalizes(self):
        from src.services.script_embedding_service import ScriptEmbeddingService

        service = ScriptEmbeddingService("key", "gemini-embedding-001", dimensions=2)
        values = service.embed_script({"hook": "Your excuses are costing you."})

        self.assertAlmostEqual(math.sqrt(sum(value * value for value in values)), 1.0)
        call = service._client.models.call
        self.assertEqual(call["model"], "gemini-embedding-001")
        self.assertEqual(call["config"].kwargs["task_type"], "SEMANTIC_SIMILARITY")
        self.assertEqual(call["config"].kwargs["output_dimensionality"], 2)


if __name__ == "__main__":
    unittest.main()
