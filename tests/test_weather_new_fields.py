import pytest
from app.services.weather_service import NOAAWeatherService


@pytest.fixture
def weather_service():
    return NOAAWeatherService()


def test_combine_weather_data_with_new_fields(weather_service):
    """Test that new weather fields are properly combined"""

    forecast_data = {
        "properties": {
            "relativeHumidity": {"values": [{"value": 75.5}]},
            "dewpoint": {"values": [{"value": 15.0}]},  # Celsius
            "probabilityOfPrecipitation": {"values": [{"value": 40.0}]},
            "quantitativePrecipitation": {"values": [{"value": 2.5}]},  # mm
        },
        "simpleForecast": {"properties": {"periods": [{"shortForecast": "Partly Sunny"}]}},
    }

    station_data = {}

    result = weather_service._combine_weather_data(forecast_data, station_data)

    # Check that new fields are present
    assert "relative_humidity_pct" in result
    assert result["relative_humidity_pct"] == 75.5

    assert "dew_point_f" in result
    # 15°C = 59°F
    assert result["dew_point_f"] == pytest.approx(59.0, abs=0.5)

    assert "precipitation_probability_pct" in result
    assert result["precipitation_probability_pct"] == 40.0

    assert "precipitation_amount_in" in result
    # 2.5mm = ~0.098 inches
    assert result["precipitation_amount_in"] == pytest.approx(0.098, abs=0.01)

    assert "conditions" in result
    assert result["conditions"] == "Partly Sunny"


def test_combine_weather_data_empty_new_fields(weather_service):
    """Test that function doesn't crash when new fields are missing"""

    forecast_data = {"properties": {"temperature": {"values": [{"value": 20.0}]}}}

    station_data = {}

    result = weather_service._combine_weather_data(forecast_data, station_data)

    # Check that result is valid even without new fields
    assert result is not None
    assert isinstance(result, dict)
    assert "captured_at" in result

    # New fields should not be in result if not provided
    assert "relative_humidity_pct" not in result
    assert "dew_point_f" not in result
    assert "precipitation_probability_pct" not in result
    assert "precipitation_amount_in" not in result


def test_weather_conditions_simple_forecast(weather_service):
    """Test that weather conditions use simple forecast with natural language terms"""

    forecast_data = {
        "properties": {},
        "simpleForecast": {
            "properties": {
                "periods": [{"shortForecast": "Sunny"}, {"shortForecast": "Cloudy"}]  # Should use first period
            }
        },
    }

    result = weather_service._combine_weather_data(forecast_data, {})

    # Should use the simple forecast term
    assert "conditions" in result
    assert result["conditions"] == "Sunny"


def test_weather_conditions_fallback_to_weather_array(weather_service):
    """Test fallback to weather array when simple forecast unavailable"""

    forecast_data = {
        "properties": {"weather": {"values": [{"value": [{"weather": "Rain Showers"}, {"weather": "Fog"}]}]}}
    }

    result = weather_service._combine_weather_data(forecast_data, {})

    # Should extract from weather array
    assert "conditions" in result
    assert "Rain Showers" in result["conditions"]
