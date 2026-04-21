#!/usr/bin/env python3
import io
import math
import os
import time
from typing import List, Tuple

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HEIGHTMAP_PATH = os.path.join(BASE_DIR, "world_heightmap.png")
LIGHTMAP_PATH = os.path.join(BASE_DIR, "world_lightmap.png")
MASK_DEBUG_PATH = os.path.join(BASE_DIR, "world_landmask_debug.png")

CENTER_LAT = 40.594988
CENTER_LON = -79.999149

# Full terrain size in meters
TERRAIN_SIZE_M = 400.0

# Use odd size so there is a true center pixel
IMAGE_SIZE = 1025

WATER_GRAY = 70
LAND_GRAY = 220

BLUR_RADIUS = 8
LAND_GROW_PASSES = 4

AZURE_MAPS_KEY = os.environ.get("AZURE_MAPS_KEY", "")
AZURE_MAPS_ENDPOINT = "https://atlas.microsoft.com"
AZURE_API_VERSION = "2024-04-01"

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

HEADERS = {
    "User-Agent": "cmra-ocean-floor-generator/1.0"
}


def meters_per_degree_lat() -> float:
    return 111320.0


def meters_per_degree_lon(lat_deg: float) -> float:
    return 111320.0 * math.cos(math.radians(lat_deg))


def bbox_from_center(lat: float, lon: float, width_m: float, height_m: float) -> Tuple[float, float, float, float]:
    dlat = (height_m / 2.0) / meters_per_degree_lat()
    dlon = (width_m / 2.0) / meters_per_degree_lon(lat)
    min_lon = lon - dlon
    min_lat = lat - dlat
    max_lon = lon + dlon
    max_lat = lat + dlat
    return min_lon, min_lat, max_lon, max_lat


def lonlat_to_pixel(lon: float, lat: float, bbox: Tuple[float, float, float, float], size: int) -> Tuple[float, float]:
    min_lon, min_lat, max_lon, max_lat = bbox
    u = (lon - min_lon) / (max_lon - min_lon)
    v = (max_lat - lat) / (max_lat - min_lat)
    return u * (size - 1), v * (size - 1)


def choose_azure_zoom_for_size(size_m: float) -> int:
    # Practical fixed choices
    if size_m <= 75:
        return 19
    if size_m <= 200:
        return 18
    if size_m <= 400:
        return 17
    return 16


def fetch_azure_imagery(center_lat: float, center_lon: float, size_m: float, out_path: str) -> None:
    if not AZURE_MAPS_KEY:
        raise RuntimeError("Set AZURE_MAPS_KEY before running this script.")

    zoom = choose_azure_zoom_for_size(size_m)
    print(f"Using Azure center request at zoom: {zoom}")

    # NOTE: Azure uses lon,lat for coordinates in request parameters
    params = {
        "api-version": AZURE_API_VERSION,
        "tilesetId": "microsoft.imagery",
        "center": f"{center_lon},{center_lat}",
        "zoom": zoom,
        "width": IMAGE_SIZE,
        "height": IMAGE_SIZE,
        "subscription-key": AZURE_MAPS_KEY,
    }

    r = requests.get(
        f"{AZURE_MAPS_ENDPOINT}/map/static",
        params=params,
        headers={**HEADERS, "Accept": "image/png"},
        timeout=60,
    )
    r.raise_for_status()

    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    img.save(out_path)
    print(f"Wrote {out_path}")


def overpass_query(bbox: Tuple[float, float, float, float]) -> dict:
    min_lon, min_lat, max_lon, max_lat = bbox

    query = f"""
    [out:json][timeout:25];
    (
      way["natural"="water"]({min_lat},{min_lon},{max_lat},{max_lon});
      relation["natural"="water"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["waterway"="riverbank"]({min_lat},{min_lon},{max_lat},{max_lon});
      relation["waterway"="riverbank"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["natural"="coastline"]({min_lat},{min_lon},{max_lat},{max_lon});
      relation["landuse"="reservoir"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["landuse"="reservoir"]({min_lat},{min_lon},{max_lat},{max_lon});
    );
    out geom;
    """

    last_error = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"Trying Overpass endpoint: {endpoint}")
            r = requests.post(
                endpoint,
                data=query.encode("utf-8"),
                headers=HEADERS,
                timeout=45,
            )
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"Overpass failed at {endpoint}: {e}")
            last_error = e
            time.sleep(1.5)

    raise last_error


def geometry_to_polygons(data: dict) -> List[Polygon]:
    polys: List[Polygon] = []

    for elem in data.get("elements", []):
        etype = elem.get("type")

        if etype == "way":
            geom = elem.get("geometry", [])
            if len(geom) < 3:
                continue

            coords = [(p["lon"], p["lat"]) for p in geom]
            if coords[0] != coords[-1]:
                coords.append(coords[0])

            try:
                poly = Polygon(coords)
                if poly.is_valid and not poly.is_empty and poly.area > 0:
                    polys.append(poly)
            except Exception:
                pass

        elif etype == "relation":
            outers = []
            inners = []

            for member in elem.get("members", []):
                geom = member.get("geometry", [])
                if len(geom) < 3:
                    continue

                coords = [(p["lon"], p["lat"]) for p in geom]
                if coords[0] != coords[-1]:
                    coords.append(coords[0])

                role = member.get("role", "")
                if role == "outer":
                    outers.append(coords)
                elif role == "inner":
                    inners.append(coords)

            for outer in outers:
                try:
                    poly = Polygon(outer, holes=inners if inners else None)
                    if poly.is_valid and not poly.is_empty and poly.area > 0:
                        polys.append(poly)
                except Exception:
                    pass

    return polys


def draw_polygons(polys: List[Polygon], bbox: Tuple[float, float, float, float], size: int) -> Image.Image:
    img = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(img)

    for poly in polys:
        geoms = [poly] if isinstance(poly, Polygon) else list(poly.geoms)

        for g in geoms:
            ext = [lonlat_to_pixel(lon, lat, bbox, size) for lon, lat in g.exterior.coords]
            if len(ext) >= 3:
                draw.polygon(ext, fill=255)

            for interior in g.interiors:
                ring = [lonlat_to_pixel(lon, lat, bbox, size) for lon, lat in interior.coords]
                if len(ring) >= 3:
                    draw.polygon(ring, fill=0)

    return img


def make_heightmap_from_watermask(water_mask: Image.Image):
    land = ImageOps.invert(water_mask)

    for _ in range(LAND_GROW_PASSES):
        land = land.filter(ImageFilter.MaxFilter(3))

    land = land.filter(ImageFilter.GaussianBlur(BLUR_RADIUS))

    out = Image.new("L", land.size)
    src = land.load()
    dst = out.load()

    w, h = land.size
    for y in range(h):
        for x in range(w):
            t = src[x, y] / 255.0
            gray = int(round(WATER_GRAY + t * (LAND_GRAY - WATER_GRAY)))
            dst[x, y] = max(0, min(255, gray))

    return out, land


def make_flat_water_heightmap():
    return Image.new("L", (IMAGE_SIZE, IMAGE_SIZE), WATER_GRAY)


def main():
    bbox = bbox_from_center(CENTER_LAT, CENTER_LON, TERRAIN_SIZE_M, TERRAIN_SIZE_M)
    print("bbox:", bbox)
    print("center lat/lon:", CENTER_LAT, CENTER_LON)

    fetch_azure_imagery(CENTER_LAT, CENTER_LON, TERRAIN_SIZE_M, LIGHTMAP_PATH)

    try:
        data = overpass_query(bbox)
        polys = geometry_to_polygons(data)

        if polys:
            merged = unary_union(polys)
            if isinstance(merged, Polygon):
                polys = [merged]
            elif isinstance(merged, MultiPolygon):
                polys = list(merged.geoms)

        water_mask = draw_polygons(polys, bbox, IMAGE_SIZE)
        heightmap, land_debug = make_heightmap_from_watermask(water_mask)

        # mark exact center pixel in debug image
        cx = IMAGE_SIZE // 2
        cy = IMAGE_SIZE // 2
        dbg = land_debug.convert("RGB")
        draw = ImageDraw.Draw(dbg)
        draw.line((cx - 12, cy, cx + 12, cy), fill=(255, 0, 0), width=2)
        draw.line((cx, cy - 12, cx, cy + 12), fill=(255, 0, 0), width=2)

        heightmap.save(HEIGHTMAP_PATH)
        dbg.save(MASK_DEBUG_PATH)

        print(f"Wrote {HEIGHTMAP_PATH}")
        print(f"Wrote {MASK_DEBUG_PATH}")
        print(f"Water polygons found: {len(polys)}")

    except Exception as e:
        print(f"Overpass unavailable, writing fallback flat-water heightmap: {e}")
        heightmap = make_flat_water_heightmap()
        heightmap.save(HEIGHTMAP_PATH)
        print(f"Wrote {HEIGHTMAP_PATH}")


if __name__ == "__main__":
    main()