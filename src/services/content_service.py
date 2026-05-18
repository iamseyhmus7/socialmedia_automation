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

    def generate_motivation_candidates(self, count: int = 5, avoid_scripts: list[dict] | None = None) -> list[dict]:
        candidate_count = max(3, min(int(count), 5))
        avoid_prompt = self._avoid_prompt(avoid_scripts or [])
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
7. Visual fields must be concrete searchable stock-video phrases, not metaphors or single abstract words.
   Good examples: "athlete training alone in dark gym", "person staring into mirror tense face close up",
   "exhausted runner breathing hard close up", "stressed person under pressure eye contact".
   Bad examples: "man", "shadow", "darkness", "mirror", "intense".
8. Create exactly 6 media_plan.video_scenes. Each item must be one concrete stock-video scene object for a separate clip,
   ordered to match hook -> body -> outro -> loop. Avoid text overlays, brands, celebrities, cartoons, and metaphors.
9. Music must be dark cinematic motivational background music with emotional build, intense feeling, and no vocals.
10. Freesound music search fields must be short keyword searches, not generation prompts:
   - media_plan.music.search_query must be 2-4 searchable words.
   - media_plan.music.backup_queries must contain 2-3 alternate 2-4 word searches.
   - Use concrete audio terms like "clock ticking cinematic", "tense piano", "cinematic drone", "sub bass cinematic", "ambient tension".
   - Do not put constraints like "no vocals", "emotional build", "motivational background music", or full sentences in search_query.
11. Do not reuse the same emotional premise, hook family, wording pattern, or visual story as any avoid example below.
    If avoid examples mention cowardice, comfort-rotting, being saved, losing, excuses, phones, or fear, move to a genuinely different premise.

{avoid_prompt}

Return only this JSON object:
{{
  "candidates": [
    {{
      "style": "aggressive_viral_motivation",
      "script": {{
        "shock_hook": "...",
        "tension_body": "...",
        "payoff_outro": "...",
        "loop_ending": "...",
        "hook": "...",
        "body": "...",
        "outro": "..."
      }},
      "voice_plan": {{
        "highlighted_words": ["word1", "word2"],
        "tone": "intense",
        "pace": "fast_then_controlled"
      }},
      "media_plan": {{
        "visual_direction": {{
          "overall_theme": "...",
          "mood": "dark cinematic human struggle",
          "color_style": "low key contrast, muted colors",
          "avoid": ["text overlays", "brands", "celebrities", "cartoons", "visual metaphors"]
        }},
        "video_scenes": [
          {{
            "scene_id": 1,
            "beat": "hook",
            "line_match": "...",
            "search_query": "...",
            "backup_queries": ["...", "..."],
            "emotion": "...",
            "camera": "close up",
            "pace": "fast"
          }}
        ],
        "music": {{
          "search_query": "2-4 searchable audio keywords",
          "backup_queries": ["2-4 searchable audio keywords", "2-4 searchable audio keywords"],
          "mood": "dark cinematic motivational emotional build",
          "volume_hint": 0.55
        }}
      }},
      "publishing": {{
        "youtube_title": "...",
        "youtube_description": "...",
        "youtube_tags": ["motivation", "shorts", "discipline", "mindset", "stoicism"]
      }}
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

    def _avoid_prompt(self, avoid_scripts: list[dict]) -> str:
        if not avoid_scripts:
            return "Avoid examples: none yet."

        lines = [
            "Avoid examples from approved history and rejected retries:",
            "Generate a different psychological angle, not just synonyms of these examples.",
        ]
        for index, item in enumerate(avoid_scripts[-6:], start=1):
            lines.append(
                "\n".join(
                    [
                        f"{index}. similarity={item.get('similarity', '')}",
                        f"   rejected_hook: {item.get('rejected_hook', '')}",
                        f"   matched_hook: {item.get('matched_hook', '')}",
                        f"   matched_body: {item.get('matched_body', '')}",
                        f"   matched_outro: {item.get('matched_outro', '')}",
                    ]
                )
            )
        return "\n".join(lines)

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
- Keep the aggressive viral retention structure inside script: shock_hook, tension_body, payoff_outro, and loop_ending.
- Keep hook 3-8 words and total spoken script 35-55 words.
- Avoid cheap cliches: believe in yourself, never give up, dream big, work hard, stay positive.
- If the hook/intro changes, update media_plan.video_scenes[0] as a concrete searchable stock-video scene tied to the new hook meaning.
- If the body/outro theme changes, update media_plan.visual_direction and media_plan.video_scenes as concrete visual scene plans, not metaphors or single abstract words.
- Keep media_plan.video_scenes at exactly 6 ordered scene objects that match the final script beat by beat.
- Keep media_plan.music.search_query aligned with the emotional sound of the script, but keep it as 2-4 Freesound search keywords.
- Keep no-vocals and emotional-build intent in media_plan.music.mood, not in search_query.
- Keep publishing.youtube_title, publishing.youtube_description, and publishing.youtube_tags aligned with the final script.
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
