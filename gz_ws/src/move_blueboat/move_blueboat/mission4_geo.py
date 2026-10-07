"""Coordinate helpers for Mission 4 local odom and WGS84 positions."""

from __future__ import annotations

import math


WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


def local_to_enu(x: float, y: float, heading_deg: float) -> tuple[float, float]:
    """Rotate Gazebo LOCAL x/y into geographic east/north offsets in meters."""
    heading = math.radians(float(heading_deg))
    east = float(x) * math.cos(heading) - float(y) * math.sin(heading)
    north = float(x) * math.sin(heading) + float(y) * math.cos(heading)
    return east, north


def local_to_wgs84(
    x: float,
    y: float,
    latitude_deg: float,
    longitude_deg: float,
    heading_deg: float,
    elevation_m: float = 0.0,
) -> tuple[float, float]:
    """Convert a short local offset into WGS84 latitude / longitude.

    Mission 4 spans only a few hundred meters, so a local tangent-plane
    conversion using WGS84 meridional and prime-vertical radii is accurate
    while avoiding an additional geodesy dependency.
    """
    east, north = local_to_enu(x, y, heading_deg)
    lat0 = math.radians(float(latitude_deg))
    sin_lat = math.sin(lat0)
    curvature = 1.0 - WGS84_E2 * sin_lat * sin_lat
    meridional_radius = (
        WGS84_A * (1.0 - WGS84_E2) / (curvature ** 1.5)
    )
    prime_vertical_radius = WGS84_A / math.sqrt(curvature)

    latitude = lat0 + north / (meridional_radius + elevation_m)
    cos_lat = math.cos(lat0)
    if abs(cos_lat) < 1e-12:
        raise ValueError("longitude conversion is undefined at the poles")
    longitude = math.radians(float(longitude_deg)) + (
        east / ((prime_vertical_radius + elevation_m) * cos_lat)
    )
    return math.degrees(latitude), math.degrees(longitude)
