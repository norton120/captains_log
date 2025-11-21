import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx
import asyncio

logger = logging.getLogger(__name__)


class NOAAWeatherService:
    """Service for fetching marine weather data from NOAA APIs"""
    
    def __init__(self):
        self.weather_api_base = "https://api.weather.gov"
        self.coops_api_base = "https://api.tidesandcurrents.noaa.gov/api/prod"
        self.timeout = httpx.Timeout(30.0)
        
    async def get_marine_conditions(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive marine weather conditions for a specific location.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            Dictionary containing weather conditions or None if unavailable
        """
        try:
            # Get weather forecast data
            forecast_data = await self._get_weather_forecast(latitude, longitude)
            
            # Try to get observational data from nearby stations
            station_data = await self._get_station_observations(latitude, longitude)
            
            # Combine and return the data
            return self._combine_weather_data(forecast_data, station_data)
            
        except Exception as e:
            logger.error(f"Error fetching weather data for {latitude}, {longitude}: {e}")
            return None
    
    async def _get_weather_forecast(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """Get weather forecast from NWS API"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Get the grid point information
                points_url = f"{self.weather_api_base}/points/{latitude:.4f},{longitude:.4f}"
                headers = {"User-Agent": "Captain's Log Marine Weather Service"}
                
                response = await client.get(points_url, headers=headers)
                if response.status_code != 200:
                    logger.warning(f"Weather API points request failed: {response.status_code}")
                    return None
                
                points_data = response.json()
                properties = points_data.get("properties", {})
                
                # Get the forecast grid data URL
                forecast_grid_url = properties.get("forecastGridData")
                if not forecast_grid_url:
                    logger.warning("No forecast grid data URL available")
                    return None
                
                # Get the detailed grid forecast
                forecast_response = await client.get(forecast_grid_url, headers=headers)
                if forecast_response.status_code != 200:
                    logger.warning(f"Forecast grid request failed: {forecast_response.status_code}")
                    return None
                
                return forecast_response.json()
                
        except Exception as e:
            logger.error(f"Error getting weather forecast: {e}")
            return None
    
    async def _get_station_observations(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """Get observational data from nearest NOAA CO-OPS station"""
        try:
            # Find nearest station (simplified - in production, you'd want a station lookup service)
            station_id = await self._find_nearest_station(latitude, longitude)
            if not station_id:
                return None
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Get current conditions from multiple products
                base_params = {
                    "station": station_id,
                    "format": "json",
                    "time_zone": "gmt",
                    "application": "captains_log"
                }
                
                # Gather data from multiple endpoints
                tasks = []
                
                # Wind data
                wind_params = {**base_params, "product": "wind", "date": "latest"}
                tasks.append(self._fetch_coops_data(client, wind_params))
                
                # Air temperature
                air_temp_params = {**base_params, "product": "air_temperature", "date": "latest"}
                tasks.append(self._fetch_coops_data(client, air_temp_params))
                
                # Water temperature
                water_temp_params = {**base_params, "product": "water_temperature", "date": "latest"}
                tasks.append(self._fetch_coops_data(client, water_temp_params))
                
                # Air pressure
                pressure_params = {**base_params, "product": "air_pressure", "date": "latest"}
                tasks.append(self._fetch_coops_data(client, pressure_params))
                
                # Execute all requests concurrently
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Combine results
                combined_data = {}
                for result in results:
                    if isinstance(result, dict) and result:
                        combined_data.update(result)
                
                return combined_data if combined_data else None
                
        except Exception as e:
            logger.error(f"Error getting station observations: {e}")
            return None
    
    async def _fetch_coops_data(self, client: httpx.AsyncClient, params: Dict[str, str]) -> Dict[str, Any]:
        """Fetch data from CO-OPS API"""
        try:
            url = f"{self.coops_api_base}/datagetter"
            response = await client.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_coops_response(data, params["product"])
            else:
                logger.warning(f"CO-OPS request failed for {params['product']}: {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching CO-OPS data for {params.get('product')}: {e}")
            return {}
    
    def _parse_coops_response(self, data: Dict[str, Any], product: str) -> Dict[str, Any]:
        """Parse CO-OPS API response and extract relevant values"""
        try:
            parsed = {}
            data_entries = data.get("data", [])
            
            if not data_entries:
                return {}
            
            # Get the most recent entry
            latest_entry = data_entries[0] if data_entries else {}
            
            if product == "wind":
                parsed.update({
                    "wind_speed_kts": float(latest_entry.get("s", 0)) if latest_entry.get("s") else None,
                    "wind_direction_deg": float(latest_entry.get("d", 0)) if latest_entry.get("d") else None,
                    "wind_gust_kts": float(latest_entry.get("g", 0)) if latest_entry.get("g") else None,
                })
            elif product == "air_temperature":
                parsed["air_temp_f"] = float(latest_entry.get("v", 0)) if latest_entry.get("v") else None
            elif product == "water_temperature":
                parsed["water_temp_f"] = float(latest_entry.get("v", 0)) if latest_entry.get("v") else None
            elif product == "air_pressure":
                parsed["barometric_pressure_mb"] = float(latest_entry.get("v", 0)) if latest_entry.get("v") else None
            
            return parsed
            
        except Exception as e:
            logger.error(f"Error parsing CO-OPS response for {product}: {e}")
            return {}
    
    async def _find_nearest_station(self, latitude: float, longitude: float) -> Optional[str]:
        """Find nearest NOAA station (simplified implementation)"""
        # This is a simplified implementation. In production, you'd want to:
        # 1. Have a database of station locations
        # 2. Calculate actual distances
        # 3. Check station capabilities for different data products
        
        # For now, return some common stations based on rough geographic regions
        if 32 <= latitude <= 48 and -125 <= longitude <= -117:  # West Coast
            if latitude >= 37:
                return "9414290"  # San Francisco
            else:
                return "9410170"  # San Diego
        elif 25 <= latitude <= 45 and -95 <= longitude <= -67:  # East Coast
            if latitude >= 40:
                return "8518750"  # The Battery, NYC
            else:
                return "8661070"  # Springmaid Pier, SC
        elif 24 <= latitude <= 31 and -90 <= longitude <= -80:  # Gulf Coast
            return "8724580"  # Key West
        
        return None  # No suitable station found
    
    def _combine_weather_data(self, forecast_data: Optional[Dict], station_data: Optional[Dict]) -> Dict[str, Any]:
        """Combine forecast and observational data into a unified weather record"""
        combined = {
            "captured_at": datetime.now(timezone.utc),
            "air_temp_f": None,
            "water_temp_f": None,
            "wind_speed_kts": None,
            "wind_direction_deg": None,
            "wind_gust_kts": None,
            "wave_height_ft": None,
            "wave_period_sec": None,
            "barometric_pressure_mb": None,
            "visibility_nm": None,
            "conditions": None,
            "forecast": None
        }
        
        # Prioritize observational data from stations
        if station_data:
            for key in ["air_temp_f", "water_temp_f", "wind_speed_kts", 
                       "wind_direction_deg", "wind_gust_kts", "barometric_pressure_mb"]:
                if key in station_data and station_data[key] is not None:
                    combined[key] = station_data[key]
        
        # Extract data from forecast if available
        if forecast_data and forecast_data.get("properties"):
            properties = forecast_data["properties"]
            
            # Try to extract current or near-term forecast values
            # This is simplified - the actual NWS grid data structure is complex
            try:
                # Wind speed
                if "windSpeed" in properties:
                    wind_values = properties["windSpeed"].get("values", [])
                    if wind_values and combined["wind_speed_kts"] is None:
                        # Convert m/s to knots (1 m/s = 1.94384 knots)
                        wind_ms = wind_values[0].get("value", 0)
                        combined["wind_speed_kts"] = round(wind_ms * 1.94384, 1) if wind_ms else None
                
                # Wind direction
                if "windDirection" in properties:
                    wind_dir_values = properties["windDirection"].get("values", [])
                    if wind_dir_values and combined["wind_direction_deg"] is None:
                        combined["wind_direction_deg"] = wind_dir_values[0].get("value")
                
                # Temperature
                if "temperature" in properties:
                    temp_values = properties["temperature"].get("values", [])
                    if temp_values and combined["air_temp_f"] is None:
                        # Convert Celsius to Fahrenheit
                        temp_c = temp_values[0].get("value", 0)
                        combined["air_temp_f"] = round((temp_c * 9/5) + 32, 1) if temp_c else None
                
                # Wave height (if available in marine forecast)
                if "waveHeight" in properties:
                    wave_values = properties["waveHeight"].get("values", [])
                    if wave_values:
                        # Convert meters to feet
                        wave_m = wave_values[0].get("value", 0)
                        combined["wave_height_ft"] = round(wave_m * 3.28084, 1) if wave_m else None
                
                # Visibility
                if "visibility" in properties:
                    vis_values = properties["visibility"].get("values", [])
                    if vis_values:
                        # Convert meters to nautical miles
                        vis_m = vis_values[0].get("value", 0)
                        combined["visibility_nm"] = round(vis_m * 0.000539957, 1) if vis_m else None
                
            except Exception as e:
                logger.warning(f"Error parsing forecast data: {e}")
        
        # Remove None values
        return {k: v for k, v in combined.items() if v is not None}


# Global instance
weather_service = NOAAWeatherService()