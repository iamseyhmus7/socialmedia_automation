from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from database import is_video_used


MIN_SHORT_HEIGHT = 1280
MIN_SHORT_RATIO = 1.55
MAX_SHORT_RATIO = 2.20


@dataclass(frozen=True)
class VideoCandidate:
    id: str
    url: str
    score: float
    source: str


def _is_short_format(width: int | float, height: int | float) -> bool:
    if not width or not height:
        return False
    ratio = float(height) / float(width)
    return height >= MIN_SHORT_HEIGHT and MIN_SHORT_RATIO <= ratio <= MAX_SHORT_RATIO


def _ordered_queries(queries: list[str], count: int, default_query: str) -> list[str]:
    if not queries:
        queries = [default_query]

    deduped = []
    seen = set()
    for query in queries:
        normalized = " ".join(str(query or "").split())
        key = normalized.lower()
        if normalized and key not in seen:
            deduped.append(normalized)
            seen.add(key)

    selected = list(deduped)
    index = 0
    while len(selected) < count and deduped:
        selected.append(deduped[index % len(deduped)])
        index += 1
    return selected


def _vertical_provider_query(search_term: str) -> str:
    text = str(search_term or "").lower()
    if "computer" in text or "screen" in text or "office" in text or "desk" in text:
        return "office computer vertical"
    if "wallet" in text or "money" in text or "cash" in text:
        return "wallet table vertical"
    if "diving board" in text or "pool" in text or "swimming" in text:
        return "diving board vertical"
    if "hand" in text and ("shaking" in text or "anxiety" in text or "anxious" in text):
        return "anxious hands vertical"
    if "rain" in text or "window" in text:
        return "rainy window person vertical"
    if "shouting" in text or "frustration" in text or "angry" in text:
        return "angry person vertical"
    if "street corner" in text or "street" in text:
        return "lonely street vertical"
    if "staring at wall" in text or "staring" in text:
        return "lonely person room vertical"
    if "mouth" in text or "speaking" in text:
        return "speaking mouth vertical"
    if "pressure" in text or "stress" in text or "stressed" in text:
        return "stressed person vertical"
    if "eyes" in text or "eye" in text:
        return "eyes close up vertical"
    if "gym" in text or "athlete" in text or "training" in text:
        return "gym vertical"
    if "phone" in text or "scroll" in text or "procrastination" in text:
        return "phone vertical"
    if "mirror" in text:
        return "mirror person vertical"
    if "determined" in text or "looking at camera" in text or "camera" in text:
        return "determined person vertical"
    if "face" in text or "close up" in text:
        return "close up face vertical"
    if "runner" in text or "running" in text:
        return "runner vertical"

    stop_words = {
        "dark",
        "moody",
        "cinematic",
        "portrait",
        "motivation",
        "motivational",
        "human",
        "motion",
        "person",
        "close",
        "looking",
        "camera",
        "alone",
        "with",
        "into",
        "under",
    }
    words = [
        word
        for word in text.replace(",", " ").split()
        if len(word) >= 4 and word not in stop_words
    ]
    core = " ".join(words[:2])
    return f"{core} vertical".strip() if core else "person vertical"


def _query_words(search_term: str) -> set[str]:
    return {
        word
        for word in str(search_term or "").lower().replace(",", " ").split()
        if len(word) >= 4
    }


def _text_match_score(text: str, search_term: str) -> float:
    lowered = str(text or "").lower()
    return float(sum(1 for word in _query_words(search_term) if word in lowered))


def _ratio_score(width: int | float, height: int | float) -> float:
    if not width or not height:
        return 0.0
    ratio = float(height) / float(width)
    return max(0.0, 1.0 - min(abs(ratio - (16 / 9)), 1.0))


def _resolution_score(width: int | float, height: int | float) -> float:
    pixels = float(width or 0) * float(height or 0)
    return min(pixels / float(1080 * 1920), 1.0)


class PexelsVideoService:
    def __init__(self, api_key: str | None, assets_dir: str):
        self.api_key = api_key
        self.assets_dir = assets_dir
        self.search_url = "https://api.pexels.com/videos/search"

    def search_videos(self, queries: list[str], count: int = 6) -> list[tuple[str, str]]:
        return [(candidate.id, candidate.url) for candidate in self.search_candidates(queries, count=count)]

    def search_candidates(self, queries: list[str], count: int = 6) -> list[VideoCandidate]:
        candidates = []
        selected_ids = set()
        headers = {"Authorization": self.api_key}

        selected_queries = _ordered_queries(queries, count, "human discipline under pressure close up")

        for query_index, search_term in enumerate(selected_queries):
            if len(candidates) >= count:
                break
            if "dark" not in search_term.lower() and "silhouette" not in search_term.lower():
                search_term = f"{search_term} dark moody cinematic"

            params = {"query": search_term, "per_page": 15, "orientation": "portrait"}
            try:
                print(f"  [VIDEO SERVICE] Searching Pexels: {search_term}", flush=True)
                response = requests.get(self.search_url, headers=headers, params=params, timeout=45)
                if response.status_code != 200:
                    response_text = getattr(response, "text", "")
                    print(
                        f"  [VIDEO SERVICE] Pexels failed with HTTP {response.status_code}: {response_text[:180]}",
                        flush=True,
                    )
                    continue
                selected_for_query = False
                for result_index, video in enumerate(response.json().get("videos", [])):
                    video_id = str(video.get("id"))
                    if video_id in selected_ids or is_video_used(video_id):
                        continue
                    best_file = self._get_best_video_file(video.get("video_files", []))
                    if best_file:
                        score = self._score_video(video, best_file, search_term, query_index, result_index)
                        candidates.append(VideoCandidate(video_id, best_file.get("link"), score, "pexels"))
                        selected_ids.add(video_id)
                        selected_for_query = True
                        break
                if not selected_for_query:
                    print("  [VIDEO SERVICE] Pexels returned no usable 9:16 short-format videos.", flush=True)
            except Exception as exc:
                print(f"  [VIDEO SERVICE] Search failed ({search_term}): {exc}", flush=True)

        return candidates

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
        short_files = [
            file
            for file in video_files
            if _is_short_format(file.get("width", 0), file.get("height", 0))
        ]
        if not short_files:
            return None
        hd_files = [file for file in short_files if file.get("width", 0) >= 720]
        candidates = hd_files or short_files
        return max(candidates, key=lambda file: file.get("width", 0) * file.get("height", 0))

    def _score_video(
        self,
        video: dict,
        video_file: dict,
        search_term: str,
        query_index: int,
        result_index: int,
    ) -> float:
        text = " ".join(str(value or "") for value in [video.get("url"), video.get("user", {}).get("name")])
        relevance_score = max(0.0, 6.0 - (result_index * 0.35) - (query_index * 0.50))
        return (
            relevance_score
            + (_text_match_score(text, search_term) * 1.5)
            + (_ratio_score(video_file.get("width", 0), video_file.get("height", 0)) * 2.0)
            + (_resolution_score(video_file.get("width", 0), video_file.get("height", 0)) * 1.5)
        )


class PixabayVideoService:
    def __init__(self, api_key: str | None, assets_dir: str):
        self.api_key = api_key
        self.assets_dir = assets_dir
        self.search_url = "https://pixabay.com/api/videos/"

    def search_videos(self, queries: list[str], count: int = 6) -> list[tuple[str, str]]:
        return [(candidate.id, candidate.url) for candidate in self.search_candidates(queries, count=count)]

    def search_candidates(self, queries: list[str], count: int = 6) -> list[VideoCandidate]:
        if not self.api_key:
            print("  [VIDEO SERVICE] PIXABAY_API_KEY is missing; skipping Pixabay videos.", flush=True)
            return []

        candidates = []
        selected_ids = set()

        selected_queries = _ordered_queries(queries, count, "human discipline under pressure close up")

        for query_index, search_term in enumerate(selected_queries):
            if len(candidates) >= count:
                break
            if "dark" not in search_term.lower() and "silhouette" not in search_term.lower():
                search_term = f"{search_term} dark moody cinematic"
            api_query = _vertical_provider_query(search_term)

            params = {
                "key": self.api_key,
                "q": api_query[:100],
                "per_page": 20,
                "safesearch": "true",
                "order": "popular",
                "video_type": "film",
                "min_height": 720,
            }
            try:
                print(f"  [VIDEO SERVICE] Searching Pixabay: {api_query} (from: {search_term})", flush=True)
                response = requests.get(self.search_url, params=params, timeout=45)
                if response.status_code != 200:
                    response_text = getattr(response, "text", "")
                    print(
                        f"  [VIDEO SERVICE] Pixabay failed with HTTP {response.status_code}: {response_text[:180]}",
                        flush=True,
                    )
                    continue
                choice = self._choose_best_video(response.json().get("hits", []), search_term, selected_ids, query_index)
                if choice:
                    candidates.append(choice)
                    selected_ids.add(choice.id)
            except Exception as exc:
                print(f"  [VIDEO SERVICE] Pixabay search failed ({search_term}): {exc}", flush=True)

        return candidates

    def download_video(self, url: str, filename: str) -> str:
        path = os.path.join(self.assets_dir, filename)
        if os.path.exists(path):
            return path
        os.makedirs(self.assets_dir, exist_ok=True)
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with open(path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
        return path

    def _get_best_video_file(self, videos: dict) -> dict | None:
        short_files = [
            video
            for video in videos.values()
            if video.get("url") and _is_short_format(video.get("width", 0), video.get("height", 0))
        ]
        if not short_files:
            return None
        return max(short_files, key=lambda video: video.get("width", 0) * video.get("height", 0))

    def _choose_best_video(
        self,
        videos: list[dict],
        search_term: str,
        selected_ids: set[str],
        query_index: int = 0,
    ) -> VideoCandidate | None:
        candidates = []
        for result_index, video in enumerate(videos):
            video_id = f"pixabay_{video.get('id')}"
            if video_id in selected_ids or is_video_used(video_id):
                continue
            best_file = self._get_best_video_file(video.get("videos", {}))
            if not best_file:
                continue
            score = self._score_video(video, best_file, search_term, query_index, result_index)
            candidates.append(VideoCandidate(video_id, best_file.get("url"), score, "pixabay"))

        if not candidates:
            print("  [VIDEO SERVICE] Pixabay returned no usable 9:16 short-format videos.", flush=True)
            return None

        return max(candidates, key=lambda candidate: candidate.score)

    def _score_video(self, video: dict, video_file: dict, search_term: str, query_index: int = 0, result_index: int = 0) -> float:
        text = " ".join(
            str(value or "").lower()
            for value in [video.get("tags"), video.get("user"), video.get("type")]
        )
        popularity_score = min(float(video.get("downloads", 0)) / 10000, 1.0)
        relevance_score = max(0.0, 5.5 - (result_index * 0.30) - (query_index * 0.50))
        return (
            relevance_score
            + (_text_match_score(text, search_term) * 2.0)
            + (_ratio_score(video_file.get("width", 0), video_file.get("height", 0)) * 2.0)
            + (_resolution_score(video_file.get("width", 0), video_file.get("height", 0)) * 1.0)
            + popularity_score
        )


class MultiSourceVideoService:
    def __init__(self, primary: PexelsVideoService, fallbacks: list[object] | None = None):
        self.primary = primary
        self.fallbacks = fallbacks or []

    def search_videos(self, queries: list[str], count: int = 6) -> list[tuple[str, str]]:
        candidates = []
        selected_ids = set()
        for provider in [self.primary, *self.fallbacks]:
            provider_candidates = self._provider_candidates(provider, queries, count)
            for candidate in provider_candidates:
                if candidate.id in selected_ids:
                    continue
                candidates.append(candidate)
                selected_ids.add(candidate.id)

        ranked = sorted(candidates, key=lambda candidate: candidate.score, reverse=True)
        selected = ranked[:count]
        if selected:
            summary = ", ".join(f"{candidate.source}:{candidate.id}={candidate.score:.2f}" for candidate in selected)
            print(f"  [VIDEO SERVICE] Selected ranked videos: {summary}", flush=True)
        return [(candidate.id, candidate.url) for candidate in selected]

    def _provider_candidates(self, provider: object, queries: list[str], count: int) -> list[VideoCandidate]:
        if hasattr(provider, "search_candidates"):
            return provider.search_candidates(queries, count=count)
        return [
            VideoCandidate(video_id, video_url, 0.0, provider.__class__.__name__.lower())
            for video_id, video_url in provider.search_videos(queries, count=count)
        ]

    def download_video(self, url: str, filename: str) -> str:
        if filename.startswith("raw_pixabay_"):
            for fallback in self.fallbacks:
                if isinstance(fallback, PixabayVideoService):
                    return fallback.download_video(url, filename)
        if filename.startswith("raw_coverr_"):
            for fallback in self.fallbacks:
                if isinstance(fallback, CoverrVideoService):
                    return fallback.download_video(url, filename)
        return self.primary.download_video(url, filename)


class CoverrVideoService:
    def __init__(self, api_key: str | None, assets_dir: str):
        self.api_key = api_key
        self.assets_dir = assets_dir
        self.search_url = "https://api.coverr.co/videos"

    def search_videos(self, queries: list[str], count: int = 6) -> list[tuple[str, str]]:
        return [(candidate.id, candidate.url) for candidate in self.search_candidates(queries, count=count)]

    def search_candidates(self, queries: list[str], count: int = 6) -> list[VideoCandidate]:
        if not self.api_key:
            print("  [VIDEO SERVICE] COVERR_API_KEY is missing; skipping Coverr videos.", flush=True)
            return []

        candidates = []
        selected_ids = set()

        selected_queries = _ordered_queries(queries, count, "human discipline under pressure close up")

        headers = {"Authorization": f"Bearer {self.api_key}"}
        for query_index, search_term in enumerate(selected_queries):
            if len(candidates) >= count:
                break
            api_query = _vertical_provider_query(search_term)
            params = {
                "query": api_query[:100],
                "page_size": 20,
                "sort": "popular",
                "urls": "true",
            }
            try:
                print(f"  [VIDEO SERVICE] Searching Coverr: {api_query} (from: {search_term})", flush=True)
                response = requests.get(self.search_url, headers=headers, params=params, timeout=45)
                if response.status_code != 200:
                    response_text = getattr(response, "text", "")
                    print(
                        f"  [VIDEO SERVICE] Coverr failed with HTTP {response.status_code}: {response_text[:180]}",
                        flush=True,
                    )
                    continue
                for result_index, video in enumerate(response.json().get("hits", [])):
                    video_id = f"coverr_{video.get('id')}"
                    if video_id in selected_ids or is_video_used(video_id):
                        continue
                    if not self._is_short_video(video):
                        continue
                    video_url = self._get_video_url(video)
                    if video_url:
                        score = self._score_video(video, search_term, query_index, result_index)
                        candidates.append(VideoCandidate(video_id, video_url, score, "coverr"))
                        selected_ids.add(video_id)
                        break
                else:
                    print("  [VIDEO SERVICE] Coverr returned no usable vertical short-format videos.", flush=True)
            except Exception as exc:
                print(f"  [VIDEO SERVICE] Coverr search failed ({search_term}): {exc}", flush=True)

        return candidates

    def download_video(self, url: str, filename: str) -> str:
        path = os.path.join(self.assets_dir, filename)
        if os.path.exists(path):
            return path
        os.makedirs(self.assets_dir, exist_ok=True)
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with open(path, "wb") as file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    file.write(chunk)
        return path

    def _get_video_url(self, video: dict) -> str | None:
        urls = video.get("urls") or {}
        return urls.get("mp4_download") or urls.get("mp4") or urls.get("mp4_preview")

    def _is_short_video(self, video: dict) -> bool:
        if video.get("is_vertical") is True:
            return True
        aspect_ratio = str(video.get("aspect_ratio") or "")
        if aspect_ratio == "9:16":
            return True
        return _is_short_format(video.get("max_width", 0), video.get("max_height", 0))

    def _score_video(self, video: dict, search_term: str, query_index: int, result_index: int) -> float:
        text = " ".join(
            str(value or "")
            for value in [
                video.get("title"),
                video.get("description"),
                video.get("tags"),
                video.get("category"),
            ]
        )
        relevance_score = max(0.0, 5.0 - (result_index * 0.30) - (query_index * 0.50))
        return (
            relevance_score
            + (_text_match_score(text, search_term) * 2.0)
            + (_ratio_score(video.get("max_width", 0), video.get("max_height", 0)) * 2.0)
            + (_resolution_score(video.get("max_width", 0), video.get("max_height", 0)) * 1.0)
        )
