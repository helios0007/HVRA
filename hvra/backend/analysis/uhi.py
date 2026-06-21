"""
Urban Heat Island (UHI) correction for Barcelona.

Derives the neighbourhood from lat/lon and applies the UHI temperature delta
to EPW outdoor temperatures before all Stage 2 health KPI calculations.

Applied as:
    T_outdoor_adjusted = T_epw + UHI_DELTA[neighbourhood]

UHI delta values:
    SOURCE: UPC (2025) Barcelona heat vulnerability study +
            Copernicus Urban Heat Island dataset (Copernicus Climate Change Service).

Neighbourhood lookup (priority order):
  1. Shapely point-in-polygon against Barcelona Open Data BARRI polygons
     (0301100100_UNITATS_ADM_POLIGONS.json, EPSG:25831).
     Query point converted from WGS84 via pyproj (Transformer.from_crs) or
     manual UTM 31N formula if pyproj is unavailable.
  2. Nearest-centroid fallback (approximate WGS84 centroids).
  3. City-average fallback (1.5°C).
"""

from __future__ import annotations
import json
import logging
import math
import os
from typing import Optional

logger = logging.getLogger(__name__)

# ── Full barri-level UHI delta table (73 Barcelona barris) ─────────────────────
# SOURCE: UPC (2025) Barcelona heat vulnerability study +
#         Copernicus Urban Heat Island dataset.
# Keys match the 'NOM' property in 0301100100_UNITATS_ADM_POLIGONS.json.
# Values represent mean nighttime UHI intensity relative to suburban reference (°C).
BARRI_UHI_DELTA: dict[str, float] = {
    # Districte 01 — Ciutat Vella
    "el Raval":                                     2.5,
    "el Barri Gòtic":                               2.0,
    "la Barceloneta":                               1.5,
    "Sant Pere, Santa Caterina i la Ribera":        2.0,
    # Districte 02 — Eixample
    "el Fort Pienc":                                2.5,
    "la Sagrada Família":                           2.5,
    "la Dreta de l'Eixample":                       2.5,
    "l'Antiga Esquerra de l'Eixample":              2.5,
    "la Nova Esquerra de l'Eixample":               2.5,
    "Sant Antoni":                                  2.5,
    # Districte 03 — Sants-Montjuïc
    "el Poble-sec":                                 1.5,
    "la Marina del Prat Vermell":                   1.0,
    "la Marina de Port":                            1.0,
    "la Font de la Guatlla":                        1.5,
    "Hostafrancs":                                  1.5,
    "la Bordeta":                                   1.5,
    "Sants - Badal":                                1.5,
    "Sants":                                        1.5,
    # Districte 04 — Les Corts
    "les Corts":                                    1.5,
    "la Maternitat i Sant Ramon":                   1.5,
    "Pedralbes":                                    0.5,
    # Districte 05 — Sarrià-Sant Gervasi
    "Vallvidrera, el Tibidabo i les Planes":        0.0,
    "Sarrià":                                       0.5,
    "les Tres Torres":                              0.5,
    "Sant Gervasi - la Bonanova":                   0.5,
    "Sant Gervasi - Galvany":                       1.0,
    "el Putxet i el Farró":                         0.5,
    # Districte 06 — Gràcia
    "Vallcarca i els Penitents":                    1.0,
    "el Coll":                                      1.0,
    "la Salut":                                     1.5,
    "la Vila de Gràcia":                            2.0,
    "el Camp d'en Grassot i Gràcia Nova":           2.0,
    # Districte 07 — Horta-Guinardó
    "el Baix Guinardó":                             1.5,
    "Can Baró":                                     1.0,
    "el Guinardó":                                  1.5,
    "la Font d'en Fargues":                         1.0,
    "el Carmel":                                    1.0,
    "la Teixonera":                                 1.0,
    "Sant Genís dels Agudells":                     0.5,
    "Montbau":                                      0.5,
    "la Vall d'Hebron":                             0.5,
    "la Clota":                                     1.0,
    "Horta":                                        1.0,
    # Districte 08 — Nou Barris
    "Vilapicina i la Torre Llobeta":                1.5,
    "Porta":                                        1.5,
    "el Turó de la Peira":                          1.5,
    "Can Peguera":                                  1.0,
    "la Guineueta":                                 1.5,
    "Canyelles":                                    1.0,
    "les Roquetes":                                 1.0,
    "Verdun":                                       1.5,
    "la Prosperitat":                               1.5,
    "la Trinitat Nova":                             1.5,
    "Torre Baró":                                   1.0,
    "Ciutat Meridiana":                             1.5,
    "Vallbona":                                     1.0,
    # Districte 09 — Sant Andreu
    "la Trinitat Vella":                            1.5,
    "Baró de Viver":                                1.5,
    "el Bon Pastor":                                1.5,
    "Sant Andreu":                                  1.5,
    "la Sagrera":                                   1.5,
    "el Congrés i els Indians":                     1.5,
    "Navas":                                        1.5,
    # Districte 10 — Sant Martí
    "el Camp de l'Arpa del Clot":                   1.5,
    "el Clot":                                      1.5,
    "el Parc i la Llacuna del Poblenou":            1.0,
    "la Vila Olímpica del Poblenou":                1.0,
    "el Poblenou":                                  1.0,
    "Diagonal Mar i el Front Marítim del Poblenou": 1.0,
    "el Besòs i el Maresme":                        1.5,
    "Provençals del Poblenou":                      1.0,
    "Sant Martí de Provençals":                     1.5,
    "la Verneda i la Pau":                          1.5,
}

# City-average fallback for unmatched locations.
# PROXY: Barcelona July average UHI ~ 1.5°C.
# SOURCE: Copernicus Urban Heat Island dataset city average.
UHI_DEFAULT = 1.5

# Path to Barcelona Open Data BARRI polygon file (EPSG:25831).
_POLIGONS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "config", "barcelona",
    "0301100100_UNITATS_ADM_POLIGONS.json",
)

# ── Approximate neighbourhood centroids (WGS84) — nearest-centroid fallback ─────
# PROXY: approximate centroids from Barcelona municipal atlas.
NEIGHBOURHOOD_CENTROIDS: dict[str, tuple[float, float]] = {
    "la Barceloneta":                               (41.3793, 2.1880),
    "la Dreta de l'Eixample":                       (41.3940, 2.1720),
    "l'Antiga Esquerra de l'Eixample":              (41.3870, 2.1560),
    "la Nova Esquerra de l'Eixample":               (41.3840, 2.1480),
    "la Vila de Gràcia":                            (41.4055, 2.1560),
    "el Clot":                                      (41.4115, 2.1940),
    "Sarrià":                                       (41.3980, 2.1090),
    "el Poblenou":                                  (41.4010, 2.2065),
    "Sants":                                        (41.3750, 2.1415),
    "les Corts":                                    (41.3850, 2.1350),
    "el Guinardó":                                  (41.4200, 2.1660),
    "la Prosperitat":                               (41.4370, 2.1780),
    "Sant Andreu":                                  (41.4290, 2.1970),
    "el Poble-sec":                                 (41.3720, 2.1620),
    "el Raval":                                     (41.3790, 2.1680),
}


def get_uhi_correction(
    lat: float,
    lon: float,
) -> tuple[str, float]:
    """
    Return (neighbourhood_name, uhi_delta_celsius) for a building at (lat, lon).

    Tries Barcelona Open Data BARRI polygon lookup first (EPSG:25831 with
    automatic coordinate reprojection), then nearest-centroid fallback.

    Parameters
    ----------
    lat, lon : float
        Building location (WGS84).
    """
    result = _polygon_lookup(lat, lon)
    if result is not None:
        name, delta = result
        logger.info("UHI: %s (polygon lookup) → +%.1f°C", name, delta)
        return name, delta

    name = _nearest_centroid(lat, lon)
    delta = BARRI_UHI_DELTA.get(name, UHI_DEFAULT)
    logger.info("UHI: %s (centroid fallback) → +%.1f°C", name, delta)
    return name, delta


def apply_uhi(T_epw: float, uhi_delta: float) -> float:
    """
    T_outdoor_adjusted = T_epw + UHI_DELTA[neighbourhood].
    SOURCE: HVRA_build_reference_4.md §Stage 1 — UHI temperature correction.
    """
    return T_epw + uhi_delta


# ── Internal helpers ────────────────────────────────────────────────────────────

def _polygon_lookup(lat: float, lon: float) -> Optional[tuple[str, float]]:
    """
    Convert WGS84 (lat, lon) to EPSG:25831 then do point-in-polygon
    against BARRI-level features in the Barcelona Open Data polygon file.

    Uses pyproj.Transformer for reprojection; falls back to manual UTM 31N
    formula if pyproj is unavailable.
    """
    try:
        from shapely.geometry import Point, shape
    except ImportError:
        return None

    if not os.path.exists(_POLIGONS_PATH):
        logger.debug("BARRI polygon file not found: %s", _POLIGONS_PATH)
        return None

    # Convert WGS84 → EPSG:25831 (UTM zone 31N) so the query point matches
    # the file's native coordinate system.
    try:
        from pyproj import Transformer
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:25831", always_xy=True)
        x_utm, y_utm = transformer.transform(lon, lat)
    except Exception:
        x_utm, y_utm = _wgs84_to_utm31n(lon, lat)

    pt = Point(x_utm, y_utm)

    try:
        with open(_POLIGONS_PATH, encoding="utf-8") as f:
            fc = json.load(f)
    except Exception as exc:
        logger.warning("Could not load BARRI polygon file: %s", exc)
        return None

    for feature in fc.get("features", []):
        props = feature.get("properties", {})
        if props.get("TIPUS_UA") != "BARRI":
            continue
        nom = (props.get("NOM") or "").strip()
        if not nom:
            continue
        try:
            poly = shape(feature["geometry"])
            if poly.contains(pt):
                delta = BARRI_UHI_DELTA.get(nom, UHI_DEFAULT)
                return nom, delta
        except Exception:
            continue

    return None


def _nearest_centroid(lat: float, lon: float) -> str:
    """Return the name of the nearest neighbourhood centroid (metric distance)."""
    best_name = "la Dreta de l'Eixample"
    best_dist = float("inf")
    lat_scale = 111_000.0
    lon_scale = 111_000.0 * math.cos(math.radians(lat))

    for name, (n_lat, n_lon) in NEIGHBOURHOOD_CENTROIDS.items():
        dy = (lat - n_lat) * lat_scale
        dx = (lon - n_lon) * lon_scale
        dist = math.hypot(dx, dy)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def _wgs84_to_utm31n(lon: float, lat: float) -> tuple[float, float]:
    """
    Manual WGS84 → UTM zone 31N (EPSG:25831) conversion.
    Accuracy ≈ 1 m — sufficient for neighbourhood-level polygon lookup.
    Used as fallback when pyproj is unavailable.
    """
    lon_rad = math.radians(lon)
    lat_rad = math.radians(lat)

    # WGS84 ellipsoid
    a = 6_378_137.0
    f = 1.0 / 298.257_223_563
    b = a * (1.0 - f)
    e2 = 1.0 - (b / a) ** 2
    e_p2 = e2 / (1.0 - e2)

    lon0 = math.radians(3.0)   # UTM zone 31 central meridian
    k0 = 0.9996

    N = a / math.sqrt(1.0 - e2 * math.sin(lat_rad) ** 2)
    T = math.tan(lat_rad) ** 2
    C = e_p2 * math.cos(lat_rad) ** 2
    A = math.cos(lat_rad) * (lon_rad - lon0)

    M = a * (
        (1.0 - e2 / 4.0 - 3.0 * e2 ** 2 / 64.0 - 5.0 * e2 ** 3 / 256.0) * lat_rad
        - (3.0 * e2 / 8.0 + 3.0 * e2 ** 2 / 32.0 + 45.0 * e2 ** 3 / 1024.0) * math.sin(2.0 * lat_rad)
        + (15.0 * e2 ** 2 / 256.0 + 45.0 * e2 ** 3 / 1024.0) * math.sin(4.0 * lat_rad)
        - (35.0 * e2 ** 3 / 3072.0) * math.sin(6.0 * lat_rad)
    )

    x = k0 * N * (
        A
        + (1.0 - T + C) * A ** 3 / 6.0
        + (5.0 - 18.0 * T + T ** 2 + 72.0 * C - 58.0 * e_p2) * A ** 5 / 120.0
    ) + 500_000.0

    y = k0 * (
        M + N * math.tan(lat_rad) * (
            A ** 2 / 2.0
            + (5.0 - T + 9.0 * C + 4.0 * C ** 2) * A ** 4 / 24.0
            + (61.0 - 58.0 * T + T ** 2 + 600.0 * C - 330.0 * e_p2) * A ** 6 / 720.0
        )
    )
    # Northern hemisphere: false northing = 0

    return x, y
