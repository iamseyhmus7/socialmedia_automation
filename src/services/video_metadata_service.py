from __future__ import annotations

from typing import Any


DEFAULT_TITLE = "Motivation"
DEFAULT_TAGS = ["motivation", "shorts", "stoicism"]


def build_upload_metadata(
    script_data: dict[str, Any] | None = None,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    script_data = script_data or {}
    hook = str(script_data.get("hook") or "").strip()
    body = str(script_data.get("body") or "").strip()
    outro = str(script_data.get("outro") or "").strip()
    resolved_tags = _dedupe_tags(tags or script_data.get("youtube_tags") or DEFAULT_TAGS)

    return {
        "title": _trim_text(title or script_data.get("youtube_title") or hook or DEFAULT_TITLE, 100),
        "description": _trim_text(
            description
            if description is not None
            else script_data.get("youtube_description")
            or _build_default_description(hook, body, outro, resolved_tags),
            5000,
        ),
        "tags": resolved_tags,
        "script_data": script_data,
    }


def _build_default_description(hook: str, body: str, outro: str, tags: list[str]) -> str:
    text = "\n\n".join(part for part in [hook, body, outro] if part)
    hashtags = " ".join(f"#{tag.replace(' ', '')}" for tag in tags[:6])
    if "#shorts" not in hashtags.lower():
        hashtags = f"#shorts {hashtags}".strip()
    return "\n\n".join(part for part in [text, hashtags] if part)


def _dedupe_tags(tags: list[str]) -> list[str]:
    result = []
    seen = set()
    for tag in tags:
        clean = str(tag).strip().lstrip("#")
        key = clean.lower()
        if clean and key not in seen:
            result.append(clean)
            seen.add(key)
    return result


def _trim_text(value: str, limit: int) -> str:
    value = " ".join(str(value).split())
    if len(value) <= limit:
        return value
    if limit <= 3:
        return value[:limit]
    return value[: limit - 3].rstrip() + "..."
