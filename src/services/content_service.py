from __future__ import annotations

import json
import re
from typing import Any


class GeminiContentService:
    def __init__(self, api_key: str | None, model_name: str):
        import google.generativeai as genai

        if api_key:
            genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def generate_motivation_quote(self) -> dict:
        candidates = self.generate_motivation_candidates(count=1)
        return candidates[0]

    def generate_motivation_candidates(self, count: int = 5) -> list[dict]:
        candidate_count = max(3, min(int(count), 5))
        prompt = f"""
You are an elite short-form retention strategist for TikTok, Reels, and YouTube Shorts.
Create aggressive viral English motivational scripts that make the viewer feel personally called out.
Avoid cheap cliches, generic advice, and soft inspirational slogans.

Generate exactly {candidate_count} different candidates.

Hard rules for every candidate:
1. The hook must be 3-8 words, direct, uncomfortable, and curiosity-driven.
2. The hook should usually address "you" directly.
3. Total spoken script must be 35-55 words across hook, body, and outro.
4. Body must create tension: problem -> inner conflict -> awareness -> decision.
5. Outro must not simply close the video; it must create a loop back to the hook.
6. Never use phrases like "believe in yourself", "never give up", "dream big", "work hard", "stay positive".
7. Visual fields must be human-focused, dark cinematic, portrait, close-up, motion, struggle, discipline, isolation, or eye contact.
8. Music must be dark cinematic motivational background music with emotional build, intense feeling, and no vocals.

Return only this JSON object:
{{
  "candidates": [
    {{
      "style": "aggressive_viral_motivation",
      "shock_hook": "...",
      "tension_body": "...",
      "payoff_outro": "...",
      "loop_ending": "...",
      "hook": "...",
      "body": "...",
      "outro": "...",
      "hook_pexels_arama_terimi": "...",
      "pexels_arama_temasi": "...",
      "pexels_anahtar_kelimeleri": ["term1", "term2", "term3"],
      "freesound_arama_terimi": "...",
      "vurgulanacak_kelimeler": ["word1", "word2"],
      "youtube_title": "...",
      "youtube_description": "...",
      "youtube_tags": ["motivation", "shorts", "discipline", "mindset", "stoicism"]
    }}
  ]
}}
"""
        prompt += "\nReturn no keys except the keys shown in the JSON schema above."
        response = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        data = self._parse_json(response.text)
        if isinstance(data, list):
            return data
        candidates = data.get("candidates") if isinstance(data, dict) else None
        if isinstance(candidates, list):
            return [candidate for candidate in candidates if isinstance(candidate, dict)]
        if isinstance(data, dict):
            return [data]
        return []

    def edit_script(self, original_script_data: dict, actions: list) -> dict:
        action_summaries = [
            {
                "target": action.target,
                "instruction": action.instruction,
                "params": action.params,
            }
            for action in actions
        ]
        prompt = f"""
Update the existing video script according to the requested edits.

Existing script JSON:
{json.dumps(original_script_data, ensure_ascii=False, indent=2)}

Requested edits:
{json.dumps(action_summaries, ensure_ascii=False, indent=2)}

Rules:
- Apply only the requested changes.
- Preserve unchanged sections and search fields unless a requested edit requires changing them.
- Keep the aggressive viral retention structure: shock_hook, tension_body, payoff_outro, and loop_ending.
- Keep hook 3-8 words and total spoken script 35-55 words.
- Avoid cheap cliches: believe in yourself, never give up, dream big, work hard, stay positive.
- If the hook/intro changes, update hook_pexels_arama_terimi so the opening shot is human-focused, close-up, tense, fast motion, dark cinematic, and tied to the new hook meaning.
- If the body/outro theme changes, update pexels_arama_temasi, pexels_anahtar_kelimeleri, and freesound_arama_terimi so visuals and music still follow the script.
- Keep youtube_title, youtube_description, and youtube_tags aligned with the final script.
- Return the complete script in the exact same JSON shape.
- Return no extra keys outside the original script schema.
"""
        response = self.model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        return self._parse_json(response.text)

    def _parse_json(self, text: str) -> Any:
        clean = text.strip()
        clean = re.sub(r"^```[a-zA-Z]*\n?", "", clean, flags=re.MULTILINE)
        clean = re.sub(r"```$", "", clean, flags=re.MULTILINE)
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            extracted = self._extract_first_json_value(clean)
            if extracted is not None:
                return extracted
            raise

    def _extract_first_json_value(self, text: str) -> Any | None:
        decoder = json.JSONDecoder()
        for index, character in enumerate(text):
            if character not in "{[":
                continue
            try:
                value, _end = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                continue
            return value
        return None
