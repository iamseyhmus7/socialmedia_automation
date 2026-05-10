from __future__ import annotations

import os
import random

import requests

from database import is_video_used


class PexelsVideoService:
    def __init__(self, api_key: str | None, assets_dir: str):
        self.api_key = api_key
        self.assets_dir = assets_dir
        self.search_url = "https://api.pexels.com/videos/search"

    def search_videos(self, queries: list[str], count: int = 6) -> list[tuple[str, str]]:
        videos_to_download = []
        selected_ids = set()
        headers = {"Authorization": self.api_key}

        if not queries:
            queries = ["dark cinematic landscape"]

        selected_queries = random.sample(queries, min(count, len(queries)))
        while len(selected_queries) < count:
            selected_queries.append(random.choice(queries))

        for search_term in selected_queries:
            if "dark" not in search_term.lower() and "silhouette" not in search_term.lower():
                search_term = f"{search_term} dark moody cinematic"

            params = {"query": search_term, "per_page": 15, "orientation": "portrait"}
            try:
                response = requests.get(self.search_url, headers=headers, params=params, timeout=45)
                if response.status_code != 200:
                    continue
                for video in response.json().get("videos", []):
                    video_id = str(video.get("id"))
                    if video_id in selected_ids or is_video_used(video_id):
                        continue
                    best_file = self._get_best_video_file(video.get("video_files", []))
                    if best_file:
                        videos_to_download.append((video_id, best_file.get("link")))
                        selected_ids.add(video_id)
                        break
            except Exception as exc:
                print(f"  [VIDEO SERVICE] Search failed ({search_term}): {exc}", flush=True)

        return videos_to_download

    def download_video(self, url: str, filename: str) -> str:
        path = os.path.join(self.assets_dir, filename)
        if os.path.exists(path):
            return path
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with open(path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
        return path

    def _get_best_video_file(self, video_files: list[dict]) -> dict | None:
        portrait_files = [
            file
            for file in video_files
            if file.get("height", 0) > file.get("width", 0) and file.get("height", 0) >= 1280
        ]
        hd_files = [file for file in portrait_files if file.get("width", 0) >= 720]
        candidates = hd_files or portrait_files or video_files
        if not candidates:
            return None
        return max(candidates, key=lambda file: file.get("width", 0) * file.get("height", 0))
