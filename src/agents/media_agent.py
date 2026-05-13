from __future__ import annotations

from src.domain.feedback import FeedbackAction
from src.domain.media import concrete_visual_query, dedupe_queries
from src.services.music_service import FreesoundMusicService
from src.services.video_service import CoverrVideoService, MultiSourceVideoService, PexelsVideoService


MUSIC_QUERY_NOISE_TERMS = {
    "background",
    "beat",
    "build",
    "emotional",
    "feeling",
    "intense",
    "motivational",
    "music",
    "no",
    "soundtrack",
    "vocals",
    "vocal",
    "with",
}


class MediaAgent:
    def __init__(
        self,
        video_service: PexelsVideoService | MultiSourceVideoService | CoverrVideoService,
        music_service: FreesoundMusicService,
    ):
        self.video_service = video_service
        self.music_service = music_service

    def download_initial_videos(self, script_data: dict) -> list[str]:
        scene_query_groups = self._build_scene_query_groups(script_data)
        video_list = []
        selected_ids = set()
        for queries in scene_query_groups:
            scene_videos = self.video_service.search_videos(queries, count=1)
            for video_id, video_url in scene_videos:
                if video_id in selected_ids:
                    continue
                video_list.append((video_id, video_url))
                selected_ids.add(video_id)
                break

        remaining_count = 6 - len(video_list)
        if remaining_count > 0:
            fallback_queries = self._build_visual_queries(script_data)
            video_list.extend(self.video_service.search_videos(fallback_queries, count=remaining_count))

        paths = []
        for index, (video_id, video_url) in enumerate(video_list):
            print(f"  [VIDEO] Downloading ({index + 1}/{len(video_list)}): {video_id}", flush=True)
            paths.append(self.video_service.download_video(video_url, f"raw_{video_id}.mp4"))
        return paths

    def media_brief(self, script_data: dict) -> dict:
        media_plan = dict(script_data.get("media_plan") or {})
        return {
            "script_context": {
                "hook": script_data.get("hook", ""),
                "body": script_data.get("body", ""),
                "outro": script_data.get("outro", ""),
            },
            "visual_direction": dict(media_plan.get("visual_direction") or {}),
            "video_scenes": self._planned_video_scenes(script_data),
            "music": self._music_plan(script_data),
        }

    def _planned_video_scenes(self, script_data: dict) -> list[dict]:
        media_plan = dict(script_data.get("media_plan") or {})
        planned_scenes = list(media_plan.get("video_scenes") or [])
        if planned_scenes:
            scenes = []
            for index, scene in enumerate(planned_scenes, start=1):
                if isinstance(scene, dict):
                    search_query = concrete_visual_query(scene.get("search_query", ""))
                    backup_queries = [
                        concrete_visual_query(query)
                        for query in list(scene.get("backup_queries") or [])
                        if str(query).strip()
                    ]
                    scenes.append(
                        {
                            **scene,
                            "scene_id": scene.get("scene_id", index),
                            "search_query": search_query,
                            "backup_queries": backup_queries,
                        }
                    )
                else:
                    scenes.append(
                        {
                            "scene_id": index,
                            "search_query": concrete_visual_query(scene),
                            "backup_queries": [],
                        }
                    )
            return scenes[:6]

        return [
            {"scene_id": index, "search_query": query, "backup_queries": []}
            for index, query in enumerate(self._build_visual_queries(script_data), start=1)
        ][:6]

    def _build_scene_query_groups(self, script_data: dict) -> list[list[str]]:
        media_plan = dict(script_data.get("media_plan") or {})
        has_planned_scenes = bool(media_plan.get("video_scenes") or script_data.get("video_sahneleri"))
        if has_planned_scenes:
            scenes = self._planned_video_scenes(script_data)
            groups = []
            for scene in scenes:
                queries = [scene.get("search_query", ""), *list(scene.get("backup_queries") or [])]
                groups.append(dedupe_queries([self._motivation_query(query) for query in queries if query]))
            return groups

        hook_query = self._build_opening_query(script_data)
        visual_queries = self._build_visual_queries(script_data)
        if hook_query:
            return [[hook_query]] + [[query] for query in visual_queries]
        return [[query] for query in visual_queries]

    def _build_visual_queries(self, script_data: dict) -> list[str]:
        media_plan = dict(script_data.get("media_plan") or {})
        planned_scenes = list(media_plan.get("video_scenes") or script_data.get("video_sahneleri") or [])
        if planned_scenes:
            raw_queries = [
                concrete_visual_query(query.get("search_query", "") if isinstance(query, dict) else query)
                for query in planned_scenes
            ]
            return dedupe_queries([self._motivation_query(query) for query in raw_queries])

        keywords = list(script_data.get("pexels_anahtar_kelimeleri") or [])
        theme = script_data.get("pexels_arama_temasi")
        if theme:
            keywords.insert(0, theme)
        if not keywords:
            keywords = ["human discipline under pressure"]
        story_beats = [
            self._script_scene_query(script_data),
            "human struggle close up eye contact",
            "alone discipline dark gym fast motion",
            "focused person under pressure cinematic portrait",
        ]
        raw_queries = [concrete_visual_query(query) for query in keywords + story_beats]
        return dedupe_queries([self._motivation_query(query) for query in raw_queries])

    def _build_opening_query(self, script_data: dict) -> str:
        parts = [
            script_data.get("hook", ""),
            script_data.get("hook_pexels_arama_terimi", ""),
            script_data.get("pexels_arama_temasi", ""),
        ]
        story_query = " ".join(str(part).strip() for part in parts if str(part).strip())
        return self._motivation_query(
            f"{story_query} intense human face close up eye contact struggle fast motion opening shot"
        )

    def _motivation_query(self, query: str) -> str:
        base = str(query).strip() or "cinematic motivation"
        required = ["dark", "cinematic", "portrait", "motivation", "human", "close up", "motion"]
        missing = [word for word in required if word not in base.lower()]
        if missing:
            base = f"{base} {' '.join(missing)}"
        return base

    def _script_scene_query(self, script_data: dict) -> str:
        text = " ".join(
            str(script_data.get(key, ""))
            for key in ["hook", "body", "outro"]
            if script_data.get(key)
        ).lower()
        if "mirror" in text:
            return "person staring into mirror tense face close up"
        if "phone" in text or "scroll" in text or "comfort" in text:
            return "person alone in dark room resisting phone procrastination"
        if "gym" in text or "discipline" in text or "train" in text:
            return "athlete training alone dark gym discipline close up"
        if "fear" in text or "pressure" in text:
            return "stressed person under pressure close up eye contact"
        return "person alone under pressure close up eye contact dark cinematic"

    def apply_video_actions(self, current_paths: list[str], actions: list[FeedbackAction]) -> list[str]:
        paths = list(current_paths)
        if any(action.target == "all" for action in actions):
            instruction_queries = [action.instruction or "dark motivation cinematic" for action in actions]
            return self._download_by_queries(instruction_queries, count=6)

        for action in actions:
            target = action.target
            if not target.startswith("video_"):
                continue
            try:
                index = int(target.split("_")[1]) - 1
            except (IndexError, ValueError):
                continue
            new_paths = self._download_by_queries([action.instruction or "dark motivation cinematic"], count=1)
            if not new_paths:
                continue
            if index < len(paths):
                paths[index] = new_paths[0]
            else:
                paths.append(new_paths[0])
        return paths

    def download_music(self, script_data: dict, tried_music_ids: list[str]) -> tuple[str | None, list[str]]:
        music_plan = self._music_plan(script_data)
        music_id = None
        music_url = None
        music_query = ""
        for raw_query in [music_plan["search_query"], *music_plan["backup_queries"]]:
            music_query = self._music_query(raw_query)
            print(f"  [MUSIC] Query: {music_query}", flush=True)
            music_id, music_url = self.music_service.search_music(music_query, exclude_ids=tried_music_ids)
            if music_url:
                break
        if not music_url:
            print("  [MUSIC] No background music was downloaded; render will continue with voiceover only.", flush=True)
            return None, tried_music_ids
        music_path = self.music_service.download_music(music_url, f"music_{music_id}.mp3")
        print(f"  [MUSIC] Ready: {music_path}", flush=True)
        return music_path, tried_music_ids + [str(music_id)]

    def _music_plan(self, script_data: dict) -> dict:
        media_plan = dict(script_data.get("media_plan") or {})
        music = dict(media_plan.get("music") or {})
        return {
            "search_query": str(
                music.get("search_query") or script_data.get("freesound_arama_terimi") or "epic motivational"
            ),
            "backup_queries": [str(query) for query in list(music.get("backup_queries") or []) if str(query).strip()],
            "volume_hint": music.get("volume_hint", 0.55),
        }

    def _music_query(self, query: str) -> str:
        words = [
            word
            for word in str(query or "").lower().replace("-", " ").replace(",", " ").split()
            if word.isalpha() and word not in MUSIC_QUERY_NOISE_TERMS
        ]
        word_set = set(words)

        if {"clock", "ticking"} <= word_set or "ticking" in word_set:
            return "clock ticking cinematic"
        if "hourglass" in word_set or "sand" in word_set:
            return "hourglass ticking cinematic"
        if "piano" in word_set:
            prefix = "tense" if "tense" in word_set or "dark" in word_set else "emotional"
            return f"{prefix} piano cinematic"
        if "drone" in word_set or "ambient" in word_set:
            return "cinematic drone"
        if "bass" in word_set or "sub" in word_set:
            return "sub bass cinematic"
        if "tension" in word_set or "suspense" in word_set:
            return "ambient tension"

        priority = [
            "cinematic",
            "dark",
            "tense",
            "piano",
            "drone",
            "ambient",
            "tension",
            "bass",
            "clock",
            "ticking",
        ]
        selected = [word for word in priority if word in word_set]
        selected.extend(word for word in words if word not in selected)
        compact = selected[:4]
        if "cinematic" not in compact:
            compact = (compact + ["cinematic"])[:4]
        return " ".join(compact) or "cinematic drone"

    def _download_by_queries(self, queries: list[str], count: int) -> list[str]:
        videos = self.video_service.search_videos(queries, count=count)
        return [self.video_service.download_video(video_url, f"raw_{video_id}.mp4") for video_id, video_url in videos]
