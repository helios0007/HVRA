#!/usr/bin/env python3
"""Test script to debug buffer zone building fetching."""
import asyncio
from services.infrared_client import get_infrared_client
from shapely.geometry import Polygon

async def test_buffer_fetch():
    # Test coordinates
    zone_geojson = {
        "type": "Polygon",
        "coordinates": [[
            [-74.0, 40.7],
            [-74.0, 40.71],
            [-73.99, 40.71],
            [-73.99, 40.7],
            [-74.0, 40.7]
        ]]
    }

    # Create buffer zone (150m)
    coords = zone_geojson['coordinates'][0]
    zone_polygon = Polygon(coords)
    buffer_degrees = 150 / 111320.0
    buffered_polygon = zone_polygon.buffer(buffer_degrees)

    exterior_coords = list(buffered_polygon.exterior.coords)
    buffer_zone_geojson = {
        "type": "Polygon",
        "coordinates": [exterior_coords]
    }

    print(f"Zone GeoJSON: {zone_geojson}")
    buffer_str = str(buffer_zone_geojson)
    print(f"Buffer GeoJSON: {buffer_str[:100]}..." if len(buffer_str) > 100 else f"Buffer GeoJSON: {buffer_zone_geojson}")

    # Fetch buildings
    client = await get_infrared_client()

    print("\nFetching zone buildings...")
    zone_area = await asyncio.to_thread(client.buildings.get_area, zone_geojson)
    print(f"Zone buildings: {len(zone_area.buildings) if zone_area.buildings else 0}")

    print("\nFetching buffer zone buildings...")
    buffer_area = await asyncio.to_thread(client.buildings.get_area, buffer_zone_geojson)
    print(f"Buffer area buildings: {len(buffer_area.buildings) if buffer_area.buildings else 0}")

    if buffer_area and buffer_area.buildings:
        print(f"Buffer area type: {type(buffer_area.buildings)}")
        if isinstance(buffer_area.buildings, dict):
            print(f"First few keys: {list(buffer_area.buildings.keys())[:5]}")

if __name__ == "__main__":
    asyncio.run(test_buffer_fetch())
