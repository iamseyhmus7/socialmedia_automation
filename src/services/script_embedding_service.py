from __future__ import annotations

import math
from typing import Any


class ScriptEmbeddingService:
    def __init__(self, api_key: str | None, model_name: str, dimensions: int = 768):
        from google import genai
        from google.genai import types

        self.model_name = model_name
        self.dimensions = int(dimensions)
        self._types = types
        self._client = genai.Client(api_key=api_key) if api_key else genai.Client()

    def embed_script(self, script_data: dict[str, Any]) -> list[float]:
        text = self.embedding_text(script_data)
        result = self._client.models.embed_content(
            model=self.model_name,
            contents=text,
            config=self._types.EmbedContentConfig(
                task_type="SEMANTIC_SIMILARITY",
                output_dimensionality=self.dimensions,
            ),
        )
        embeddings = list(getattr(result, "embeddings", []) or [])
        if not embeddings:
            raise RuntimeError("Gemini embedding response did not include embeddings.")
        values = [float(value) for value in embeddings[0].values]
        return self._normalize(values)

    def embedding_text(self, script_data: dict[str, Any]) -> str:
        script_section = dict(script_data.get("script") or {})
        media_plan = dict(script_data.get("media_plan") or {})
        visual_direction = dict(media_plan.get("visual_direction") or {})
        scenes = list(media_plan.get("video_scenes") or script_data.get("video_sahneleri") or [])

        scene_queries = []
        for scene in scenes:
            if isinstance(scene, dict):
                query = scene.get("search_query") or scene.get("line_match")
            else:
                query = scene
            if query:
                scene_queries.append(str(query))

        fields = [
            script_section.get("hook") or script_data.get("hook"),
            script_section.get("body") or script_data.get("body"),
            script_section.get("outro") or script_data.get("outro"),
            script_section.get("loop_ending") or script_data.get("loop_ending"),
            script_data.get("hook_pexels_arama_terimi"),
            script_data.get("pexels_arama_temasi"),
            " ".join(str(value) for value in script_data.get("pexels_anahtar_kelimeleri") or []),
            visual_direction.get("overall_theme"),
            visual_direction.get("mood"),
            " ".join(scene_queries),
        ]
        return "\n".join(str(value).strip() for value in fields if str(value or "").strip())

    def _normalize(self, values: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in values))
        if not norm:
            return values
        return [value / norm for value in values]
