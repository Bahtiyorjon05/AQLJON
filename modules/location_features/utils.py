"""
Shared utilities for location features
Centralized functions to avoid code duplication
"""
import math

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the distance between two points using the haversine formula

    Args:
        lat1: Latitude of first point
        lon1: Longitude of first point
        lat2: Latitude of second point
        lon2: Longitude of second point

    Returns:
        Distance in kilometers
    """
    R = 6371  # Earth radius in kilometers

    # Convert degrees to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    # Differences in coordinates
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    # Haversine formula
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    # Distance in kilometers
    distance = R * c
    return distance

def validate_city_name(city_name: str) -> tuple[bool, str]:
    """
    Validate city name input

    Args:
        city_name: City name to validate

    Returns:
        Tuple of (is_valid, cleaned_city_name)
    """
    if not city_name or not str(city_name).strip():
        return False, ""

    cleaned = str(city_name).strip()

    # Check length
    if len(cleaned) < 2:
        return False, cleaned

    # Check for invalid characters (optional - allow Unicode for international cities)
    # For now, just ensure it's not empty after stripping

    return True, cleaned

def validate_coordinates(latitude: float, longitude: float) -> bool:
    """
    Validate geographic coordinates

    Args:
        latitude: Latitude value
        longitude: Longitude value

    Returns:
        True if valid, False otherwise
    """
    try:
        lat = float(latitude)
        lon = float(longitude)

        # Check ranges
        if lat < -90 or lat > 90:
            return False
        if lon < -180 or lon > 180:
            return False

        return True
    except (ValueError, TypeError):
        return False
