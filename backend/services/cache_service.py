import json
import hashlib
import os
from config import Config
from typing import Dict, Optional

class AnalysisCache:
    """Simple file-based cache for zone analysis results to avoid re-running expensive Infrared analysis."""

    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or os.path.join(Config.UPLOAD_DIR, 'analysis_cache')
        os.makedirs(self.cache_dir, exist_ok=True)

    def get_cache_key(self, zone_geojson: Dict) -> str:
        """
        Generate a cache key based on zone geometry.
        Uses SHA256 hash of the normalized GeoJSON to handle variations in formatting.
        """
        # Extract just the geometry (coordinates) to create cache key
        # This ensures same geometry = same cache, regardless of other metadata
        geom_str = json.dumps(zone_geojson, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(geom_str.encode()).hexdigest()[:16]

    def get(self, zone_geojson: Dict) -> Optional[Dict]:
        """Retrieve cached analysis results if available."""
        cache_key = self.get_cache_key(zone_geojson)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")

        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Cache read error for {cache_key}: {e}")
                return None
        return None

    def set(self, zone_geojson: Dict, analysis_result: Dict) -> bool:
        """Store analysis results in cache."""
        cache_key = self.get_cache_key(zone_geojson)
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")

        try:
            with open(cache_file, 'w') as f:
                json.dump(analysis_result, f)
            return True
        except Exception as e:
            print(f"Cache write error for {cache_key}: {e}")
            return False

    def clear(self):
        """Clear all cached analyses."""
        try:
            for file in os.listdir(self.cache_dir):
                if file.endswith('.json'):
                    os.remove(os.path.join(self.cache_dir, file))
            return True
        except Exception as e:
            print(f"Cache clear error: {e}")
            return False

# Global cache instance
_cache = None

def get_cache():
    global _cache
    if _cache is None:
        _cache = AnalysisCache()
    return _cache
