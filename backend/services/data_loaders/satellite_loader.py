import datetime
import logging
from typing import Dict, Optional, Tuple

import numpy as np
import requests

logger = logging.getLogger(__name__)

# Barcelona-wide bbox used as the UHI baseline ("city mean")
CITY_BBOX = (2.05, 41.32, 2.25, 41.47)


class SatelliteLoader:
    """
    Real NDVI and Land Surface Temperature from free satellite archives.
    No account or API key required:

    - NDVI: Sentinel-2 L2A COGs via AWS Earth Search STAC
      (https://earth-search.aws.element84.com/v1, AWS Open Data)
    - LST: Landsat 8/9 Collection 2 Level-2 surface temperature via
      Microsoft Planetary Computer STAC (anonymous SAS token signing)
      ST band scaling per USGS C2 L2: K = DN * 0.00341802 + 149.0
    """

    EARTH_SEARCH = "https://earth-search.aws.element84.com/v1/search"
    PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
    PC_SAS = "https://planetarycomputer.microsoft.com/api/sas/v1/token/landsat-c2-l2"

    def __init__(self):
        self.cache = {}

    @staticmethod
    def _search_window() -> str:
        """Last 12 months, so there is always a recent low-cloud scene."""
        now = datetime.datetime.now(datetime.timezone.utc)
        start = now - datetime.timedelta(days=365)
        return f"{start.strftime('%Y-%m-%dT00:00:00Z')}/{now.strftime('%Y-%m-%dT23:59:59Z')}"

    @staticmethod
    def _read_window(href: str, bbox: Tuple[float, float, float, float]) -> Optional[np.ndarray]:
        """Windowed read of a remote COG, bbox in WGS84 (west, south, east, north)."""
        import rasterio
        from rasterio.warp import transform_bounds
        from rasterio.windows import from_bounds

        with rasterio.open(href) as src:
            wb = transform_bounds("EPSG:4326", src.crs, *bbox)
            win = from_bounds(*wb, src.transform)
            data = src.read(1, window=win)
            return data.astype("float32")

    def get_ndvi(self, bbox: Tuple[float, float, float, float]) -> Optional[Dict]:
        """
        Mean NDVI for a bbox (west, south, east, north) from the least-cloudy
        Sentinel-2 L2A scene of the last year. 10m resolution.
        """
        cache_key = f"ndvi_{bbox}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            r = requests.post(self.EARTH_SEARCH, json={
                "collections": ["sentinel-2-l2a"],
                "bbox": list(bbox),
                "datetime": self._search_window(),
                "query": {"eo:cloud_cover": {"lt": 10}},
                "limit": 1,
                "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
            }, timeout=30)
            r.raise_for_status()
            features = r.json().get("features", [])
            if not features:
                logger.warning("[SATELLITE] No low-cloud Sentinel-2 scene found")
                return None
            item = features[0]

            red = self._read_window(item["assets"]["red"]["href"], bbox)
            nir = self._read_window(item["assets"]["nir"]["href"], bbox)
            mask = (red > 0) & (nir > 0)
            if not mask.any():
                return None
            ndvi = (nir - red) / (nir + red + 1e-9)
            valid = ndvi[mask]

            result = {
                "mean_ndvi": float(valid.mean()),
                "max_ndvi": float(valid.max()),
                "green_fraction": float((valid > 0.4).mean()),  # share of vegetated pixels
                "scene_id": item["id"],
                "scene_date": item["properties"].get("datetime", "")[:10],
                "cloud_cover": item["properties"].get("eo:cloud_cover"),
                "source": "Sentinel-2 L2A (AWS Earth Search)",
            }
            logger.info(
                f"[SATELLITE] NDVI from {result['scene_id']}: "
                f"mean={result['mean_ndvi']:.3f}, green_fraction={result['green_fraction']:.2f}"
            )
            self.cache[cache_key] = result
            return result

        except Exception as e:
            logger.error(f"[SATELLITE] NDVI fetch failed: {e}")
            return None

    def get_lst(self, bbox: Tuple[float, float, float, float]) -> Optional[Dict]:
        """
        Land surface temperature (deg C) for a bbox from the least-cloudy
        summer-capable Landsat 8/9 C2 L2 scene of the last year, plus the
        city-wide mean from the SAME scene for a true UHI delta. 30m resolution.
        """
        cache_key = f"lst_{bbox}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            r = requests.post(self.PC_STAC, json={
                "collections": ["landsat-c2-l2"],
                "bbox": list(bbox),
                "datetime": self._search_window(),
                "query": {
                    "eo:cloud_cover": {"lt": 20},
                    "platform": {"in": ["landsat-8", "landsat-9"]},
                },
                "limit": 10,
                "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
            }, timeout=30)
            r.raise_for_status()
            features = r.json().get("features", [])
            if not features:
                logger.warning("[SATELLITE] No low-cloud Landsat scene found")
                return None

            # Prefer warm-season scenes (May-Sep): that's when heat risk peaks
            def is_summer(item):
                month = int(item["properties"]["datetime"][5:7])
                return 5 <= month <= 9

            summer = [f for f in features if is_summer(f)]
            item = (summer or features)[0]

            token = requests.get(self.PC_SAS, timeout=30).json()["token"]
            href = item["assets"]["lwir11"]["href"] + "?" + token

            def lst_celsius(box):
                data = self._read_window(href, box)
                valid = data[data > 0]
                if valid.size == 0:
                    return None
                return valid * 0.00341802 + 149.0 - 273.15

            zone_lst = lst_celsius(bbox)
            city_lst = lst_celsius(CITY_BBOX)
            if zone_lst is None:
                return None

            zone_mean = float(zone_lst.mean())
            city_mean = float(city_lst.mean()) if city_lst is not None else None

            result = {
                "zone_lst_c": zone_mean,
                "zone_lst_max_c": float(zone_lst.max()),
                "city_lst_c": city_mean,
                "uhi_delta_c": (zone_mean - city_mean) if city_mean is not None else None,
                "scene_id": item["id"],
                "scene_date": item["properties"].get("datetime", "")[:10],
                "cloud_cover": item["properties"].get("eo:cloud_cover"),
                "source": "Landsat C2 L2 ST (Microsoft Planetary Computer)",
            }
            logger.info(
                f"[SATELLITE] LST from {result['scene_id']} ({result['scene_date']}): "
                f"zone={zone_mean:.1f}C, city={city_mean}, "
                f"UHI delta={result['uhi_delta_c']}"
            )
            self.cache[cache_key] = result
            return result

        except Exception as e:
            logger.error(f"[SATELLITE] LST fetch failed: {e}")
            return None
