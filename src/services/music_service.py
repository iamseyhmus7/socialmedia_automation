from __future__ import annotations

import os
import random

import requests

from database import is_music_used


FALLBACK_MUSIC_QUERIES = [
    "cinematic drone",
    "dark ambient",
    "suspense drone",
    "epic cinematic",
    "emotional piano",
    "motivational cinematic",
    "ambient tension",
]


class FreesoundMusicService:
    def __init__(self, api_key: str | None, assets_dir: str):
        self.api_key = api_key
        self.assets_dir = assets_dir
        self.search_url = "https://freesound.org/apiv2/search/text/"

    def search_music(
        self,
        query: str = "cinematic motivational emotional build no vocals",
        exclude_ids: list[str] | None = None,
        is_fallback: bool = False,
    ) -> tuple[str | None, str | None]:
        exclude_ids = exclude_ids or []
        if not self.api_key:
            print("  [MUSIC SERVICE] FREESOUND_API_KEY is missing; skipping background music.", flush=True)
            return None, None

        for search_query in self._search_queries(query, is_fallback):
            result = self._search_single_query(search_query, exclude_ids)
            if result != (None, None):
                return result

        print("  [MUSIC SERVICE] No usable background music found after all fallback queries.", flush=True)
        return None, None

    def _search_queries(self, query: str, is_fallback: bool) -> list[str]:
        normalized = str(query or "").strip()
        if is_fallback:
            return FALLBACK_MUSIC_QUERIES

        queries = [normalized] if normalized else []
        for fallback_query in FALLBACK_MUSIC_QUERIES:
            if fallback_query.lower() != normalized.lower():
                queries.append(fallback_query)
        return queries

    def _search_single_query(self, query: str, exclude_ids: list[str]) -> tuple[str | None, str | None]:
        print(f"  [MUSIC SERVICE] Searching Freesound: {query}", flush=True)
        params = {
            "query": query,
            "token": self.api_key,
            "fields": "id,name,previews,duration,avg_rating,num_downloads",
            "filter": "duration:[15 TO 240]",
            "sort": "downloads_desc",
            "page_size": 25,
        }
        try:
            response = requests.get(self.search_url, params=params, timeout=45)
            if response.status_code != 200:
                response_text = getattr(response, "text", "")
                print(
                    f"  [MUSIC SERVICE] Search failed with HTTP {response.status_code}: {response_text[:180]}",
                    flush=True,
                )
                return None, None
            results = response.json().get("results", [])
            if not results:
                print("  [MUSIC SERVICE] No results for query.", flush=True)
                return None, None

            filtered = [
                item
                for item in results
                if str(item.get("id")) not in exclude_ids
                and not is_music_used(str(item.get("id")))
                and item.get("previews", {}).get("preview-hq-mp3")
            ]
            if not filtered:
                print("  [MUSIC SERVICE] Results were already used, excluded, or missing MP3 previews.", flush=True)
                return None, None

            sound = random.choice(filtered[: min(5, len(filtered))])
            preview_url = sound.get("previews", {}).get("preview-hq-mp3")
            print(f"  [MUSIC SERVICE] Found: {sound.get('name')}", flush=True)
            return str(sound.get("id")), preview_url
        except Exception as exc:
            print(f"  [MUSIC SERVICE] Search failed: {exc}", flush=True)
            return None, None

    def download_music(self, url: str, filename: str) -> str:
        path = os.path.join(self.assets_dir, filename)
        if os.path.exists(path):
            print(f"  [MUSIC SERVICE] Using cached music: {path}", flush=True)
            return path
        os.makedirs(self.assets_dir, exist_ok=True)
        print(f"  [MUSIC SERVICE] Downloading music preview: {filename}", flush=True)
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        with open(path, "wb") as file:
            file.write(response.content)
        print(f"  [MUSIC SERVICE] Saved music: {path} ({len(response.content)} bytes)", flush=True)
        return path
