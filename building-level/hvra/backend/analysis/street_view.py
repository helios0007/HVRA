"""
Stage 5b — Street View facade photo fetch.

Fetches a real street-level photo of the building, oriented to look at a
specific facade, for use as the base image in AI retrofit renderings
(render.py). Falls back to None (caller uses a viewport screenshot instead)
if no API key is configured or Street View has no coverage at the location.

Heading convention matches the rest of the pipeline: 0=N, 90=E, 180=S, 270=W
(ifc_parser._wall_orientation / _compass_label) — a facade's outward normal
bearing is also the camera heading needed to look AT that facade, since
Street View "heading" is the direction the camera faces, and a camera
standing on the street facing the building looks toward the facade's
outward-normal direction reversed... in practice: heading = facade bearing
points the camera the same direction the facade faces, which is what we want
when the camera is positioned across the street from that face.

SOURCE: Google Maps Platform — Street View Static API.
"""

from __future__ import annotations
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

STREET_VIEW_ENDPOINT = "https://maps.googleapis.com/maps/api/streetview"
STREET_VIEW_METADATA_ENDPOINT = "https://maps.googleapis.com/maps/api/streetview/metadata"


def _api_key() -> str:
    return os.environ.get("GOOGLE_STREETVIEW_API_KEY", "").strip()


async def fetch_facade_photo(
    lat: float,
    lon: float,
    heading_deg: float,
    *,
    size: str = "1024x768",
    fov: int = 80,
    pitch: int = 0,
) -> Optional[bytes]:
    """
    Fetch a Street View photo looking toward the given heading from the
    building's coordinates. Returns JPEG bytes, or None if unavailable
    (no API key, no coverage, or request error) — caller should fall back
    to a viewport screenshot in that case.
    """
    api_key = _api_key()
    if not api_key:
        logger.info("GOOGLE_STREETVIEW_API_KEY not set — skipping Street View fetch")
        return None

    params = {
        "size": size,
        "location": f"{lat},{lon}",
        "heading": round(heading_deg % 360, 1),
        "fov": fov,
        "pitch": pitch,
        "key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Check coverage first — the image endpoint returns a generic
            # "no imagery" placeholder image instead of an HTTP error, so we
            # can't tell success from failure without checking metadata.
            meta_resp = await client.get(STREET_VIEW_METADATA_ENDPOINT, params=params)
            meta_resp.raise_for_status()
            meta = meta_resp.json()
            if meta.get("status") != "OK":
                logger.info("Street View has no coverage at %.5f,%.5f (status=%s)",
                            lat, lon, meta.get("status"))
                return None

            img_resp = await client.get(STREET_VIEW_ENDPOINT, params=params)
            img_resp.raise_for_status()
            return img_resp.content
    except Exception as exc:
        logger.warning("Street View fetch failed: %s", exc)
        return None
