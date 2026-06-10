"""Pexels API helper — search and cache stock photos for marketing backgrounds.

Use:
    bg_path = await fetch_for_query("Indian family worried hospital bill", lang="en")
    bg_path will be a local Path under uploads/marketing/pexels/<sha>.jpg
"""
from __future__ import annotations
import os
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import Optional

logger = logging.getLogger("sarathi.pexels")

PEXELS_BASE = "https://api.pexels.com/v1"
CACHE_DIR = Path(__file__).parent / "uploads" / "marketing" / "pexels"


def _api_key() -> str:
    return os.getenv("PEXELS_API_KEY", "").strip()


def is_enabled() -> bool:
    return bool(_api_key())


async def search_photos(query: str, orientation: str = "portrait",
                        per_page: int = 10) -> list[dict]:
    """Search Pexels. orientation: portrait | landscape | square. Returns photo dicts."""
    if not is_enabled():
        return []
    try:
        import httpx
    except ImportError:
        logger.warning("httpx not installed; cannot fetch Pexels")
        return []
    headers = {"Authorization": _api_key()}
    params = {"query": query, "per_page": str(per_page), "orientation": orientation}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{PEXELS_BASE}/search", headers=headers, params=params)
        if r.status_code != 200:
            logger.warning("Pexels search %d: %s", r.status_code, r.text[:200])
            return []
        return r.json().get("photos", []) or []
    except Exception as e:
        logger.warning("Pexels search failed: %s", e)
        return []


async def download(url: str, dest: Path) -> bool:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        logger.warning("Pexels download failed: %s", e)
        return False


async def fetch_for_query(query: str, orientation: str = "portrait") -> Optional[Path]:
    """Search + download + cache. Returns a local Path or None.
    Cached by SHA256 of (query, orientation) — same query reuses same image."""
    if not is_enabled() or not query:
        return None
    key = hashlib.sha256(f"{query}|{orientation}".encode()).hexdigest()[:16]
    cached = CACHE_DIR / f"{key}.jpg"
    if cached.exists():
        return cached
    photos = await search_photos(query, orientation, per_page=5)
    if not photos:
        return None
    # Pick top — Pexels orders by relevance + curated quality
    photo = photos[0]
    src = (photo.get("src") or {}).get("large2x") or (photo.get("src") or {}).get("large")
    if not src:
        return None
    ok = await download(src, cached)
    return cached if ok else None
