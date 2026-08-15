from app.schemas.trip import WeatherInfo
from app.services.amap_client import get_weather, get_weather_forecast


def fetch_weather(city: str, travel_date: str = "") -> WeatherInfo:
    try:
        info = get_weather(city, travel_date)
    except Exception:
        info = WeatherInfo(city=city, travel_date=travel_date)

    try:
        forecasts = get_weather_forecast(city)
    except Exception:
        forecasts = []

    info.forecasts = forecasts
    return info
