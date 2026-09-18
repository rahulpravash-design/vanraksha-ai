"""Spatial primitives. Pure standard library so the engine stays dependency-free."""

from __future__ import annotations

import math
from typing import Iterable, Sequence

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two WGS84 points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def centroid(points: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """Mean position of lat/lon pairs, computed on the unit sphere.

    Averaging degrees directly is wrong near the antimeridian and at high
    latitudes; projecting to 3D first costs almost nothing and is always right.
    """
    if not points:
        raise ValueError("centroid() requires at least one point")

    x = y = z = 0.0
    for lat, lon in points:
        rlat, rlon = math.radians(lat), math.radians(lon)
        x += math.cos(rlat) * math.cos(rlon)
        y += math.cos(rlat) * math.sin(rlon)
        z += math.sin(rlat)

    n = len(points)
    x, y, z = x / n, y / n, z / n
    hyp = math.sqrt(x * x + y * y)
    if hyp < 1e-12 and abs(z) < 1e-12:
        return points[0]
    return math.degrees(math.atan2(z, hyp)), math.degrees(math.atan2(y, x))


def bounding_radius_km(points: Sequence[tuple[float, float]]) -> float:
    """Distance from the centroid to the furthest member point."""
    if len(points) < 2:
        return 0.0
    clat, clon = centroid(points)
    return max(haversine_km(clat, clon, lat, lon) for lat, lon in points)


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Set overlap, used to compare the syndromic profile of two reports."""
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    union = sa | sb
    if not union:
        return 1.0
    return len(sa & sb) / len(union)
