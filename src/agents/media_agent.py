from __future__ import annotations

from src.domain.feedback import FeedbackAction
from src.services.music_service import FreesoundMusicService
from src.services.video_service import PexelsVideoService


class MediaAgent:
    def __init__(self, video_service: PexelsVideoService, music_service: FreesoundMusicService):
        self.video_service = video_service
        self.music_service = music_service

    def download_initial_videos(self, script_data: dict) -> list[str]:
        hook_query = self._build_opening_query(script_data)
        pexels_queries = self._build_visual_queries(script_data)
        video_list = []
        if hook_query:
            video_list.extend(self.video_service.search_videos([hook_query], count=1))

        remaining_count = 6 - len(video_list)
        if remaining_count > 0:
            video_list.extend(self.video_service.search_videos(pexels_queries, count=remaining_count))

        paths = []
        for index, (video_id, video_url) in enumerate(video_list):
            print(f"  [VIDEO] Downloading ({index + 1}/{len(video_list)}): {video_id}", flush=True)
            paths.append(self.video_service.download_video(video_url, f"raw_{video_id}.mp4"))
        return paths

    def _build_visual_queries(self, script_data: dict) -> list[str]:
        keywords = list(script_data.get("pexels_anahtar_kelimeleri") or [])
        theme = script_data.get("pexels_arama_temasi")
        if theme:
            keywords.insert(0, theme)
        if not keywords:
            keywords = ["human discipline under pressure"]
        story_beats = [
            "human struggle close up eye contact",
            "alone discipline dark gym fast motion",
            "focused person under pressure cinematic portrait",
        ]
        return [self._motivation_query(query) for query in keywords + story_beats]

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
        music_query = self._music_query(script_data.get("freesound_arama_terimi", "epic motivational"))
        print(f"  [MUSIC] Query: {music_query}", flush=True)
        music_id, music_url = self.music_service.search_music(music_query, exclude_ids=tried_music_ids)
        if not music_url:
            print("  [MUSIC] No background music was downloaded; render will continue with voiceover only.", flush=True)
            return None, tried_music_ids
        music_path = self.music_service.download_music(music_url, f"music_{music_id}.mp3")
        print(f"  [MUSIC] Ready: {music_path}", flush=True)
        return music_path, tried_music_ids + [str(music_id)]

    def _music_query(self, query: str) -> str:
        base = str(query).strip() or "epic motivational"
        required = ["dark", "cinematic", "motivational", "emotional build", "intense", "no vocals"]
        missing = [term for term in required if term not in base.lower()]
        if missing:
            base = f"{base} {' '.join(missing)}"
        return base

    def _download_by_queries(self, queries: list[str], count: int) -> list[str]:
        videos = self.video_service.search_videos(queries, count=count)
        return [self.video_service.download_video(video_url, f"raw_{video_id}.mp4") for video_id, video_url in videos]
