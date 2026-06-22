"""
Stage 5b — AI retrofit visualisation.

Generates a photorealistic "after retrofit" image by editing a real photo
(Street View, falling back to a 3D viewport screenshot supplied by the
frontend) with Gemini's image-editing model. One render per (room, strategy)
pair — never automatic, always user-triggered from the strategy card.

Only strategies with a visible exterior or interior physical change are
supported — behavioural protocols (Category C) and material-only colour
changes better served by the existing WallSection diagram are excluded
(see RENDERABLE_STRATEGIES).

SOURCE: Google Gemini API — image generation / editing via generate_content
with response_modalities=["IMAGE"].
"""

from __future__ import annotations
import io
import logging
import os
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.5-flash-image"

# Strategies eligible for AI rendering, and whether they need an EXTERIOR
# photo (Street View / outdoor viewport shot) or an INTERIOR one (indoor
# viewport shot — Street View cannot see inside a room).
# Prompts are written from each strategy's own strategy_library.json notes —
# not invented descriptions — so the render matches what the strategy
# actually claims to do.
#
# Shared localisation preamble for exterior shading strategies: forces Gemini
# to (1) first identify every visible window opening on the facade, (2) apply
# the SAME shading element to ALL of them as one coherent design — not a
# single window, not a texture over the whole image — and (3) leave every
# other surface (wall, balconies, street, sky, neighbouring buildings)
# pixel-identical to the source photo. Image editing models default to
# over-applying a requested texture across the full frame unless explicitly
# constrained to specific objects, which is what caused the diamond-mesh
# whole-image overlay seen in early testing.
_SHADING_LOCALISATION = (
    "First identify every window opening visible on this facade. Apply the "
    "modification described below identically to EVERY window as one "
    "coherent, consistent facade-wide shading design — not just one window, "
    "and not as a texture or pattern covering the wall, balconies, doors, "
    "street, sky, or any other surface. The shading element must be clearly "
    "attached at and bounded by each window's frame, sized to that window's "
    "opening. Do not modify, recolour, or texture anything outside the "
    "window openings — the wall material, balcony railings, street, "
    "pavement, parked cars, other buildings, and sky must remain pixel-"
    "identical to the source photo."
)

RENDERABLE_STRATEGIES: dict[str, dict] = {
    "external_shading_louvers": {
        "view": "exterior",
        "prompt": (
            _SHADING_LOCALISATION + " Shading element: a modern fixed "
            "external HORIZONTAL louver screen (brise-soleil) mounted as a "
            "shallow projecting box above each window opening, sized to "
            "that window's width — like a contemporary architectural sun "
            "hood, NOT floor-to-ceiling vertical bars and NOT a cage or "
            "prison-bar appearance. The slats are wide, flat, horizontal "
            "blades stacked with visible gaps between them, angled slightly "
            "downward, in a light warm-toned timber or matte light-grey "
            "aluminium finish. The screen should read as a sleek, minimal "
            "architectural accent that complements the building's existing "
            "facade character, not an industrial or institutional grille."
        ),
    },
    "window_external_shutters": {
        "view": "exterior",
        "prompt": (
            _SHADING_LOCALISATION + " Shading element: traditional "
            "Barcelona-style external folding shutters (persianes) — "
            "slatted panels mounted in a shutter box above each window "
            "opening, shown half-open or fully extended to one side, sized "
            "exactly to that window's frame. Dark green, brown, or grey "
            "wood/composite colour, matching typical Barcelona residential "
            "shutters."
        ),
    },
    "operable_external_sunscreen": {
        "view": "exterior",
        "prompt": (
            _SHADING_LOCALISATION + " Shading element: a retractable "
            "external fabric sunscreen with a visible housing/guide-rail "
            "system mounted directly above each window opening, sized to "
            "that window's width, shown deployed at an angle to shade the "
            "glazing. Neutral fabric colour (beige, grey, or off-white)."
        ),
    },
    "green_pergola": {
        "view": "exterior",
        "prompt": (
            _SHADING_LOCALISATION + " Shading element: a light metal or "
            "timber trellis standing slightly off the wall, sized to each "
            "ground-floor or terrace window opening, with dense green "
            "climbing plants (ivy, jasmine) growing across it. Only apply "
            "to windows that are at ground floor or open onto a terrace/"
            "balcony — leave upper-floor windows with no direct ground "
            "access unchanged."
        ),
    },
    "window_enlargement": {
        "view": "exterior",
        "prompt": (
            "Identify the window openings visible on this facade. Enlarge "
            "ONE window opening to roughly 40% larger than its current "
            "size, keeping the same architectural style, frame material, "
            "and glazing type as the existing windows, plausibly integrated "
            "into the surrounding wall (adjust the masonry/render around it "
            "to look structurally real). Do not modify any other window, "
            "the rest of the wall, balconies, street, sky, or neighbouring "
            "buildings — they must remain pixel-identical to the source photo."
        ),
    },
    "internal_blinds": {
        "view": "interior",
        "prompt": (
            "Identify the window in this room. Add an internal roller "
            "blind installed at the head of that window only, shown "
            "partially lowered, light neutral fabric colour, sized exactly "
            "to the window opening. Do not modify the rest of the room — "
            "furniture, walls, floor, lighting, and the view through the "
            "window must remain pixel-identical to the source photo."
        ),
    },
}


def is_renderable(strategy_id: str) -> bool:
    return strategy_id in RENDERABLE_STRATEGIES


def render_view_type(strategy_id: str) -> Optional[str]:
    """Returns 'exterior' or 'interior', or None if not renderable."""
    entry = RENDERABLE_STRATEGIES.get(strategy_id)
    return entry["view"] if entry else None


async def generate_retrofit_render(
    base_image_bytes: bytes,
    strategy_id: str,
    room_name: str = "",
    orientation: str = "",
    custom_prompt: str = "",
) -> bytes:
    """
    Edit base_image_bytes (JPEG/PNG) to show the given strategy applied,
    using Gemini's image-editing model. Returns PNG bytes of the result.

    custom_prompt : str, optional
        User-supplied styling instructions (e.g. "make the louvers dark
        bronze metal, angled steeper"), appended to the strategy's base
        prompt rather than replacing it — so the localisation constraints
        (only modify the window area, leave everything else unchanged)
        still apply even when the user customises the look.

    Raises RuntimeError if GEMINI_API_KEY is unset, the strategy has no
    render prompt, or the model returns no image part.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set — add it to backend/.env to enable AI rendering. "
            "Get a key at https://aistudio.google.com"
        )

    entry = RENDERABLE_STRATEGIES.get(strategy_id)
    if not entry:
        raise RuntimeError(f"Strategy '{strategy_id}' is not eligible for AI rendering")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    base_image = Image.open(io.BytesIO(base_image_bytes))

    context = ""
    if room_name or orientation:
        context = f" This is the {orientation or ''} facade of '{room_name}'.".strip()

    custom = ""
    if custom_prompt.strip():
        custom = (
            f" Additional styling instructions from the user (apply these "
            f"on top of the constraints above, without violating them): "
            f"{custom_prompt.strip()}"
        )

    prompt = entry["prompt"] + context + custom + (
        " Photorealistic architectural visualisation, same lighting, same camera "
        "angle, same time of day as the source photo."
    )

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=[base_image, prompt],
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )

    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if getattr(part, "inline_data", None) is not None:
                img = part.as_image()
                if img.image_bytes is None:
                    continue
                # Re-encode through PIL to guarantee PNG output regardless of
                # the mime type Gemini actually returned (img.mime_type may
                # be JPEG/WebP) — the cache file and frontend both assume PNG.
                pil_img = Image.open(io.BytesIO(img.image_bytes))
                buf = io.BytesIO()
                pil_img.save(buf, format="PNG")
                return buf.getvalue()

    raise RuntimeError("Gemini response contained no image — try a different strategy or photo")
