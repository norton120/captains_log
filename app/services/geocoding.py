"""Geocoding service for converting coordinates to human-readable locations."""

import asyncio
import logging
from typing import Optional, Dict, Any
import aiohttp
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LocationInfo:
    """Enhanced location information."""
    latitude: float
    longitude: float
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    formatted_address: Optional[str] = None
    body_of_water: Optional[str] = None
    nearest_port: Optional[str] = None


class GeocodingService:
    """Service for reverse geocoding coordinates to location information."""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.nominatim_url = "https://nominatim.openstreetmap.org/reverse"
        self.user_agent = "CaptainsLog/1.0"
        # Rate limiting: Nominatim allows 1 request per second
        self._last_request_time = 0
        self._min_interval = 1.0
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def _rate_limit(self):
        """Ensure we don't exceed Nominatim's rate limits."""
        import time
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()
    
    async def reverse_geocode(self, latitude: float, longitude: float) -> Optional[LocationInfo]:
        """
        Reverse geocode coordinates to get location information.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            LocationInfo object with enhanced location data, or None if geocoding fails
        """
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            await self._rate_limit()
            
            params = {
                "format": "json",
                "lat": str(latitude),
                "lon": str(longitude),
                "zoom": 10,  # City level detail
                "addressdetails": 1,
                "extratags": 1,
                "namedetails": 1
            }
            
            headers = {
                "User-Agent": self.user_agent
            }
            
            logger.info(f"Reverse geocoding coordinates: {latitude}, {longitude}")
            
            async with self.session.get(
                self.nominatim_url, 
                params=params, 
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    logger.warning(f"Nominatim API returned status {response.status}")
                    return None
                
                data = await response.json()
                return self._parse_nominatim_response(data, latitude, longitude)
                
        except asyncio.TimeoutError:
            logger.error("Geocoding request timed out")
            return None
        except Exception as e:
            logger.error(f"Error during reverse geocoding: {e}")
            return None
    
    def _parse_nominatim_response(self, data: Dict[str, Any], lat: float, lon: float) -> Optional[LocationInfo]:
        """Parse Nominatim API response into LocationInfo."""
        try:
            address = data.get("address", {})
            
            # Extract location components
            city = (
                address.get("city") or 
                address.get("town") or 
                address.get("village") or
                address.get("municipality") or
                address.get("hamlet")
            )
            
            state = (
                address.get("state") or 
                address.get("province") or
                address.get("region")
            )
            
            country = address.get("country")
            
            # Format a nice address
            formatted_parts = []
            if city:
                formatted_parts.append(city)
            if state:
                formatted_parts.append(state)
            if country:
                formatted_parts.append(country)
            
            formatted_address = ", ".join(formatted_parts) if formatted_parts else None
            
            # Try to identify water bodies (useful for ship's log)
            body_of_water = None
            extratags = data.get("extratags", {})
            
            # Check for water-related tags
            if "water" in extratags:
                body_of_water = extratags["water"]
            elif address.get("body_of_water"):
                body_of_water = address["body_of_water"]
            elif "natural" in extratags and extratags["natural"] in ["bay", "strait", "sound"]:
                body_of_water = data.get("display_name", "").split(",")[0]
            
            # Try to find nearest port (this is basic - could be enhanced)
            nearest_port = None
            if "harbour" in address:
                nearest_port = address["harbour"]
            elif "port" in data.get("display_name", "").lower():
                # Extract port name if mentioned in display name
                display_name = data.get("display_name", "")
                parts = display_name.split(",")
                for part in parts:
                    if "port" in part.lower():
                        nearest_port = part.strip()
                        break
            
            location_info = LocationInfo(
                latitude=lat,
                longitude=lon,
                city=city,
                state=state,
                country=country,
                formatted_address=formatted_address,
                body_of_water=body_of_water,
                nearest_port=nearest_port
            )
            
            logger.info(f"Geocoded to: {formatted_address}")
            return location_info
            
        except Exception as e:
            logger.error(f"Error parsing geocoding response: {e}")
            return None


def format_location_enhanced(location_info: LocationInfo) -> str:
    """
    Format enhanced location information for display.
    
    Args:
        location_info: LocationInfo object with geocoded data
        
    Returns:
        Formatted location string
    """
    # Start with coordinates
    coord_str = f"{location_info.latitude:.4f}°, {location_info.longitude:.4f}°"
    
    parts = [coord_str]
    
    # Add formatted address if available
    if location_info.formatted_address:
        parts.append(location_info.formatted_address)
    
    # Add water body if we're on/near water (relevant for ship's log)
    if location_info.body_of_water:
        parts.append(f"near {location_info.body_of_water}")
    
    # Add nearest port if identified
    if location_info.nearest_port:
        parts.append(f"closest port: {location_info.nearest_port}")
    
    return " | ".join(parts)


def format_location_simple(lat: float, lon: float, city: Optional[str] = None, 
                          state: Optional[str] = None, country: Optional[str] = None) -> str:
    """
    Simple location formatting for backward compatibility.
    
    Args:
        lat: Latitude
        lon: Longitude
        city: City name
        state: State/region name
        country: Country name
        
    Returns:
        Formatted location string
    """
    coord_str = f"{lat:.4f}°, {lon:.4f}°"
    
    location_parts = []
    if city:
        location_parts.append(city)
    if state:
        location_parts.append(state)
    if country:
        location_parts.append(country)
    
    if location_parts:
        return f"{coord_str} | {', '.join(location_parts)}"
    else:
        return coord_str