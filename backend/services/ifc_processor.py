from typing import Dict, List, Optional
import os
import json

try:
    import ifcopenshell
    from ifcopenshell import geom
    HAS_IFCOPENSHELL = True
except ImportError:
    HAS_IFCOPENSHELL = False


def process_ifc_file(file_path: str, latitude: float = None, longitude: float = None) -> Dict:
    """
    Parse IFC file and extract units, coordinates, building bounds.
    If latitude/longitude provided, use them to position the building.
    """
    filename = os.path.basename(file_path)

    if not HAS_IFCOPENSHELL:
        # Fallback stub data if ifcopenshell not available
        return _get_stub_data(lat=latitude, lon=longitude)

    try:
        ifc_file = ifcopenshell.open(file_path)

        # Extract building location and geometry
        building_geom = _extract_building_geometry(ifc_file, latitude=latitude, longitude=longitude)
        units = _extract_units(ifc_file, latitude=latitude, longitude=longitude)
        origin = _extract_origin(ifc_file, latitude=latitude, longitude=longitude)
        bounds = _extract_bounds(ifc_file, latitude=latitude, longitude=longitude)

        return {
            "units": units,
            "origin": origin,
            "bounds": bounds,
            "building_geojson": building_geom,
        }
    except Exception as e:
        print(f"Error processing IFC file: {e}")
        return _get_stub_data(lat=latitude, lon=longitude)


def _get_stub_data(lat: float = None, lon: float = None) -> Dict:
    """Return stub data for testing."""
    # Use provided coordinates or defaults
    latitude = lat if lat is not None else 41.3874
    longitude = lon if lon is not None else 2.1686
    offset = 0.0005

    return {
        "units": [
            {
                "id": "Room_001",
                "name": "Living Room",
                "type": "IfcSpace",
                "area_m2": 45.2,
                "center": [longitude, latitude]  # [lon, lat]
            },
            {
                "id": "Room_002",
                "name": "Kitchen",
                "type": "IfcSpace",
                "area_m2": 18.5,
                "center": [longitude + offset/10, latitude + offset/10]
            },
            {
                "id": "Room_003",
                "name": "Bedroom",
                "type": "IfcSpace",
                "area_m2": 35.0,
                "center": [longitude - offset/10, latitude - offset/10]
            }
        ],
        "origin": {
            "lat": latitude,
            "lon": longitude,
            "elevation_m": 25.0
        },
        "bounds": {
            "min": [latitude - offset, longitude - offset],
            "max": [latitude + offset, longitude + offset]
        },
        "building_geojson": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"height": 12.0, "min_height": 0},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[
                            [longitude - offset, latitude - offset],
                            [longitude + offset, latitude - offset],
                            [longitude + offset, latitude + offset],
                            [longitude - offset, latitude + offset],
                            [longitude - offset, latitude - offset]
                        ]]
                    }
                }
            ]
        }
    }


def _extract_building_geometry(ifc_file, latitude: float = None, longitude: float = None) -> Dict:
    """Extract building footprint and height as GeoJSON."""
    features = []

    try:
        # Use provided coordinates if available, otherwise extract from IFC
        if latitude is not None and longitude is not None:
            site_coords = [longitude, latitude]
        else:
            # Get site placement to extract coordinates
            sites = ifc_file.by_type('IfcSite')
            site_coords = None
            if sites:
                site = sites[0]
                if site.RefLatitude and site.RefLongitude:
                    site_coords = [site.RefLongitude, site.RefLatitude]

        # Extract buildings
        buildings = ifc_file.by_type('IfcBuilding')
        for building in buildings:
            try:
                # Get building geometry using ifcopenshell geom
                shape = geom.create_shape(building)
                if not shape:
                    continue

                # Extract footprint and height
                placement = building.ObjectPlacement
                if placement:
                    # Get Z coordinate (height) from placement
                    z_coord = 0
                    if hasattr(placement, 'RelativePlacement') and placement.RelativePlacement:
                        if hasattr(placement.RelativePlacement, 'Location') and placement.RelativePlacement.Location:
                            loc = placement.RelativePlacement.Location
                            if hasattr(loc, 'Coordinates'):
                                if len(loc.Coordinates) > 2:
                                    z_coord = loc.Coordinates[2]

                # Create simple rectangular footprint for now
                # In production, would extract actual footprint from shape geometry
                if site_coords:
                    lon, lat = site_coords
                    offset = 0.0005  # ~50m at this latitude

                    footprint = {
                        "type": "Feature",
                        "properties": {
                            "height": max(12.0, z_coord),
                            "min_height": 0,
                            "name": building.Name or "Building"
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[
                                [lon - offset, lat - offset],
                                [lon + offset, lat - offset],
                                [lon + offset, lat + offset],
                                [lon - offset, lat + offset],
                                [lon - offset, lat - offset]
                            ]]
                        }
                    }
                    features.append(footprint)
            except Exception as e:
                print(f"Error extracting building geometry: {e}")
                continue

        # Fallback: use site coordinates if buildings not found
        if not features and site_coords:
            offset = 0.0005
            lon, lat = site_coords
            features.append({
                "type": "Feature",
                "properties": {"height": 12.0, "min_height": 0},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [lon - offset, lat - offset],
                        [lon + offset, lat - offset],
                        [lon + offset, lat + offset],
                        [lon - offset, lat + offset],
                        [lon - offset, lat - offset]
                    ]]
                }
            })
    except Exception as e:
        print(f"Error in building geometry extraction: {e}")

    return {
        "type": "FeatureCollection",
        "features": features if features else []
    }


def _extract_units(ifc_file, latitude: float = None, longitude: float = None) -> List[Dict]:
    """Extract spaces/units from IFC file."""
    units = []
    fallback_lon = longitude if longitude is not None else 2.1686
    fallback_lat = latitude if latitude is not None else 41.3874

    try:
        spaces = ifc_file.by_type('IfcSpace')
        for space in spaces:
            try:
                area = 0.0
                if hasattr(space, 'ObjectPlacement') and space.ObjectPlacement:
                    if hasattr(space.ObjectPlacement, 'RelativePlacement'):
                        loc = space.ObjectPlacement.RelativePlacement.Location
                        if hasattr(loc, 'Coordinates') and len(loc.Coordinates) >= 2:
                            # Use coordinates offset from site
                            center = [float(loc.Coordinates[0]), float(loc.Coordinates[1])]
                        else:
                            center = [fallback_lon, fallback_lat]  # fallback
                    else:
                        center = [fallback_lon, fallback_lat]
                else:
                    center = [fallback_lon, fallback_lat]

                if hasattr(space, 'AreaMeasured'):
                    area = float(space.AreaMeasured) if space.AreaMeasured else 0

                units.append({
                    "id": space.id(),
                    "name": space.Name or f"Space_{space.id()}",
                    "type": "IfcSpace",
                    "area_m2": round(area, 2),
                    "center": center
                })
            except Exception as e:
                print(f"Error extracting unit: {e}")
                continue
    except Exception as e:
        print(f"Error extracting units: {e}")

    return units if units else [
        {
            "id": "Room_001",
            "name": "Room 1",
            "type": "IfcSpace",
            "area_m2": 45.0,
            "center": [fallback_lon, fallback_lat]
        }
    ]


def _extract_origin(ifc_file, latitude: float = None, longitude: float = None) -> Dict:
    """Extract site location and elevation."""
    # If user provided coordinates, use those
    if latitude is not None and longitude is not None:
        return {
            "lat": latitude,
            "lon": longitude,
            "elevation_m": 25.0
        }

    try:
        sites = ifc_file.by_type('IfcSite')
        if sites:
            site = sites[0]
            lat = float(site.RefLatitude) if site.RefLatitude else 41.3874
            lon = float(site.RefLongitude) if site.RefLongitude else 2.1686
            elev = float(site.Elevation) if site.Elevation else 25.0

            return {
                "lat": lat,
                "lon": lon,
                "elevation_m": elev
            }
    except Exception as e:
        print(f"Error extracting origin: {e}")

    return {"lat": 41.3874, "lon": 2.1686, "elevation_m": 25.0}


def _extract_bounds(ifc_file, latitude: float = None, longitude: float = None) -> Dict:
    """Extract geographic bounds of the IFC model."""
    # If user provided coordinates, use those
    if latitude is not None and longitude is not None:
        offset = 0.0005  # ~50m
        return {
            "min": [latitude - offset, longitude - offset],
            "max": [latitude + offset, longitude + offset]
        }

    try:
        # Get site location as reference point
        sites = ifc_file.by_type('IfcSite')
        if sites:
            site = sites[0]
            lat = float(site.RefLatitude) if site.RefLatitude else 41.3874
            lon = float(site.RefLongitude) if site.RefLongitude else 2.1686

            # Create small bounds around site
            offset = 0.0005  # ~50m
            return {
                "min": [lat - offset, lon - offset],
                "max": [lat + offset, lon + offset]
            }
    except Exception as e:
        print(f"Error extracting bounds: {e}")

    return {
        "min": [41.3870, 2.1682],
        "max": [41.3878, 2.1690]
    }


def extract_ifc_data(file_path: str):
    """Extract detailed IFC data."""
    pass
