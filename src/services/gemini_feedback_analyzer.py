from __future__ import annotations

import json
import re
from typing import Any

from src.domain.feedback import FeedbackPlan
from src.services.feedback_validator import FeedbackPlanValidator


class GeminiFeedbackAnalyzer:
    def __init__(self, api_key: str | None, model_name: str, validator: FeedbackPlanValidator | None = None):
        import google.generativeai as genai

        self.validator = validator or FeedbackPlanValidator()
        if api_key:
            genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def analyze(self, user_text: str, video_count: int = 0) -> FeedbackPlan:
        for attempt in range(2):
            prompt = self._build_prompt(user_text, repair_mode=attempt == 1)
            try:
                response = self.model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"},
                )
                raw = self._parse_json(response.text)
                return self.validator.validate(raw, raw_message=user_text, video_count=video_count)
            except Exception as exc:
                last_error = exc

        return FeedbackPlan.clarify(user_text, f"Could not parse Gemini feedback safely: {last_error}")

    def _parse_json(self, text: str) -> dict[str, Any]:
        clean = text.strip()
        clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean)
        clean = re.sub(r"```$", "", clean)
        try:
            data = json.loads(clean)
        except json.JSONDecodeError:
            match = re.search(r"(\{.*\})", clean, re.DOTALL)
            if not match:
                raise
            data = json.loads(match.group(1))
        if not isinstance(data, dict):
            raise ValueError("Gemini response must be a JSON object.")
        return data

    def _build_prompt(self, user_text: str, repair_mode: bool = False) -> str:
        repair = "Return ONLY corrected valid JSON. Do not explain.\n" if repair_mode else ""
        return f"""
{repair}You are a strict intent planner for a short-form video production system.
The user can give Turkish or English feedback and can include MULTIPLE requests in one message.
Return a single JSON object. Never return markdown.

Supported action types:
- edit_script: change intro/body/outro/all script text.
- edit_video: replace video_1..video_6, video_last, or all clips.
- retry_music: choose a new background music track.
- retry_render: render-only technical changes such as music_volume.
- approve: user accepts the current video.
- cancel: user wants to stop the job.
- clarify: feedback is ambiguous.

Rules:
- If there is cancel intent, return only cancel.
- If approve appears together with change requests, ignore approve and return the changes.
- Split combined requests into multiple actions.
- Use target intro for opening/giris/giriş/hook sentence.
- Use edit_script target intro when the user asks "hook daha sert", "daha viral", "daha vurucu", or "hook degistir".
- Use edit_script target all when the user asks for a more aggressive, faster, darker, more emotional, or higher-retention script.
- Include instructions like "make the hook more aggressive", "add loop ending", "increase tension", or "remove cliches" when relevant.
- Use target video_last for final/son video.
- Use target music_volume when the user asks to raise/lower music volume.
- For music volume, put params.volume_multiplier, e.g. 1.3 for louder and 0.7 for quieter.
- Confidence must be 0.0 to 1.0. Use clarify below 0.55.

JSON schema:
{{
  "status": "approved|needs_changes|cancelled|clarify",
  "actions": [
    {{
      "type": "edit_script|edit_video|retry_music|retry_render|approve|cancel|clarify",
      "target": "intro|body|outro|all|video_1|video_2|video_3|video_4|video_5|video_6|video_last|music|music_volume",
      "instruction": "English technical summary",
      "params": {{}},
      "confidence": 0.0
    }}
  ]
}}

User feedback: {json.dumps(user_text, ensure_ascii=False)}
"""
