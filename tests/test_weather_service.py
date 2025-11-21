import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
import httpx

from app.services.weather_service import NOAAWeatherService


@pytest.fixture
def weather_service():
    return NOAAWeatherService()


@pytest.fixture
def mock_weather_forecast_response():
    """Mock response from NOAA weather API"""
    return {
        "properties": {
            "windSpeed": {"values": [{"value": 5.0}]},  # m/s
            "windDirection": {"values": [{"value": 180.0}]},  # degrees
            "temperature": {"values": [{"value": 20.0}]},  # Celsius
            "waveHeight": {"values": [{"value": 1.5}]},  # meters
            "visibility": {"values": [{"value": 5000.0}]}  # meters
        }
    }


@pytest.fixture
def mock_coops_wind_response():
    """Mock response from NOAA CO-OPS wind API"""
    return {
        "data": [
            {
                "t": "2025-01-01 12:00",
                "s": "10.5",  # wind speed knots
                "d": "270",   # wind direction degrees
                "g": "15.2"   # gust speed knots
            }
        ]
    }


@pytest.fixture
def mock_coops_temp_response():
    """Mock response from NOAA CO-OPS temperature API"""
    return {
        "data": [
            {
                "t": "2025-01-01 12:00",
                "v": "72.5"  # temperature Fahrenheit
            }
        ]
    }


@pytest.mark.asyncio
async def test_get_marine_conditions_success(
    weather_service, 
    mock_weather_forecast_response,
    mock_coops_wind_response,
    mock_coops_temp_response
):
    """Test successful weather data retrieval"""
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock the points API response
        points_response = MagicMock()
        points_response.status_code = 200
        points_response.json.return_value = {
            "properties": {
                "forecastGridData": "https://api.weather.gov/gridpoints/TEST/1,1"
            }
        }
        
        # Mock the forecast grid response
        forecast_response = MagicMock()
        forecast_response.status_code = 200
        forecast_response.json.return_value = mock_weather_forecast_response
        
        # Mock CO-OPS responses
        wind_response = MagicMock()
        wind_response.status_code = 200
        wind_response.json.return_value = mock_coops_wind_response
        
        air_temp_response = MagicMock()
        air_temp_response.status_code = 200
        air_temp_response.json.return_value = mock_coops_temp_response
        
        water_temp_response = MagicMock()
        water_temp_response.status_code = 200
        water_temp_response.json.return_value = mock_coops_temp_response
        
        pressure_response = MagicMock()
        pressure_response.status_code = 200
        pressure_response.json.return_value = {"data": []}
        
        # Configure mock client to return appropriate responses
        mock_client.get.side_effect = [
            points_response,           # Points API
            forecast_response,         # Forecast grid API
            wind_response,            # Wind data
            air_temp_response,        # Air temperature
            water_temp_response,      # Water temperature
            pressure_response         # Pressure data
        ]
        
        # Mock the station finding
        with patch.object(weather_service, '_find_nearest_station', return_value='9414290'):
            result = await weather_service.get_marine_conditions(37.7749, -122.4194)
        
        # Verify result
        assert result is not None
        assert isinstance(result, dict)
        
        # Check that we got data from both forecast and observations
        assert 'captured_at' in result
        assert isinstance(result['captured_at'], datetime)
        
        # Check observational data (prioritized)
        assert result.get('wind_speed_kts') == 10.5
        assert result.get('wind_direction_deg') == 270.0
        assert result.get('wind_gust_kts') == 15.2
        assert result.get('air_temp_f') == 72.5
        
        # Check forecast data
        assert result.get('visibility_nm') == pytest.approx(2.7, abs=0.1)  # 5000m to nm


@pytest.mark.asyncio
async def test_get_marine_conditions_api_failure(weather_service):
    """Test handling of API failures"""
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock API failure
        mock_client.get.side_effect = httpx.RequestError("Network error")
        
        result = await weather_service.get_marine_conditions(37.7749, -122.4194)
        
        assert result is None


@pytest.mark.asyncio
async def test_get_marine_conditions_no_station(weather_service):
    """Test handling when no suitable station is found"""
    
    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock successful points/forecast API but no station
        points_response = MagicMock()
        points_response.status_code = 200
        points_response.json.return_value = {
            "properties": {
                "forecastGridData": "https://api.weather.gov/gridpoints/TEST/1,1"
            }
        }
        
        forecast_response = MagicMock()
        forecast_response.status_code = 200
        forecast_response.json.return_value = {"properties": {}}
        
        mock_client.get.side_effect = [points_response, forecast_response]
        
        # Mock no station found
        with patch.object(weather_service, '_find_nearest_station', return_value=None):
            result = await weather_service.get_marine_conditions(37.7749, -122.4194)
        
        # Should still return result from forecast data only
        assert result is not None
        assert 'captured_at' in result


def test_find_nearest_station(weather_service):
    """Test station finding logic"""
    
    # West Coast
    station = weather_service._find_nearest_station(37.7749, -122.4194)  # San Francisco
    assert station == "9414290"
    
    station = weather_service._find_nearest_station(32.7157, -117.1611)  # San Diego
    assert station == "9410170"
    
    # East Coast
    station = weather_service._find_nearest_station(40.7128, -74.0060)  # NYC
    assert station == "8518750"
    
    station = weather_service._find_nearest_station(33.7490, -78.9008)  # Myrtle Beach
    assert station == "8661070"
    
    # Gulf Coast
    station = weather_service._find_nearest_station(24.5551, -81.7800)  # Key West
    assert station == "8724580"
    
    # Unknown location
    station = weather_service._find_nearest_station(0.0, 0.0)
    assert station is None


def test_parse_coops_response(weather_service):
    """Test parsing of CO-OPS API responses"""
    
    # Test wind data parsing
    wind_data = {
        "data": [
            {"t": "2025-01-01 12:00", "s": "10.5", "d": "270", "g": "15.2"}
        ]
    }
    result = weather_service._parse_coops_response(wind_data, "wind")
    assert result["wind_speed_kts"] == 10.5
    assert result["wind_direction_deg"] == 270.0
    assert result["wind_gust_kts"] == 15.2
    
    # Test temperature data parsing
    temp_data = {
        "data": [
            {"t": "2025-01-01 12:00", "v": "72.5"}
        ]
    }
    result = weather_service._parse_coops_response(temp_data, "air_temperature")
    assert result["air_temp_f"] == 72.5
    
    # Test empty data
    empty_data = {"data": []}
    result = weather_service._parse_coops_response(empty_data, "wind")
    assert result == {}


def test_combine_weather_data(weather_service):
    """Test combining forecast and observational data"""
    
    forecast_data = {
        "properties": {
            "windSpeed": {"values": [{"value": 5.0}]},
            "temperature": {"values": [{"value": 20.0}]}
        }
    }
    
    station_data = {
        "wind_speed_kts": 12.0,  # Should override forecast
        "air_temp_f": 75.0
    }
    
    result = weather_service._combine_weather_data(forecast_data, station_data)
    
    # Observational data should be prioritized
    assert result["wind_speed_kts"] == 12.0
    assert result["air_temp_f"] == 75.0
    assert "captured_at" in result
    assert isinstance(result["captured_at"], datetime)


@pytest.mark.asyncio
async def test_weather_service_integration(weather_service):
    """Integration test with mock external APIs"""
    
    # This test would normally require network access
    # For now, just verify the service can be instantiated
    assert weather_service.weather_api_base == "https://api.weather.gov"
    assert weather_service.coops_api_base == "https://api.tidesandcurrents.noaa.gov/api/prod"
    assert weather_service.timeout.total == 30.0