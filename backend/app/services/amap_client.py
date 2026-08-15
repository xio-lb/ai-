import math
import re
from datetime import date, datetime, timedelta
import os
import threading
import time
from urllib.parse import quote

import httpx
from dotenv import load_dotenv


from app.schemas.trip import (
    AttractionCandidate,
    DayPlan,
    FoodCandidate,
    HotelCandidate,
    NearbyPoi,
    RouteInfo,
    TripPlan,
    TripRequest,
    WeatherForecast,
    WeatherInfo,
)

load_dotenv()

from app.services import cache_service
from app.services.progress import report_progress

AMAP_KEY = os.getenv("AMAP_WEB_KEY")
AMAP_URL = "https://restapi.amap.com/v3/place/text"
WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"
ROUTE_URL = "https://restapi.amap.com/v3/direction/driving"
WALKING_URL = "https://restapi.amap.com/v3/direction/walking"
TRANSIT_URL = "https://restapi.amap.com/v3/direction/transit/integrated"
BICYCLING_URL = "https://restapi.amap.com/v3/direction/bicycling"
AROUND_URL = "https://restapi.amap.com/v3/place/around"
GEO_URL = "https://restapi.amap.com/v3/geocode/geo"

_center_cache: dict[str, tuple[float, float]] = {}
_amap_lock = threading.Lock()
_poi_cache: dict[tuple, list[dict]] = {}
_route_cache: dict[tuple, RouteInfo] = {}

POI_CACHE_TTL_SECONDS = 7 * 24 * 3600
ROUTE_CACHE_TTL_SECONDS = 24 * 3600
WEATHER_CACHE_TTL_SECONDS = 30 * 60
CENTER_CACHE_TTL_SECONDS = 30 * 24 * 3600

ATTRACTION_TYPE_HINTS = [
    "风景名胜",
    "旅游景点",
    "公园",
    "动物园",
    "植物园",
    "水族馆",
    "博物馆",
    "寺庙",
    "国家级景点",
]
SKIP_TYPE_HINTS = [
    "交通设施服务",
    "地名地址信息",
    "市政设施",
]


def _city_center(city: str) -> tuple[float, float]:
    if city in _center_cache:
        return _center_cache[city]

    cached = cache_service.get_cached("amap", f"center:{city}")
    if cached is not None:
        lng, lat = float(cached[0]), float(cached[1])
        _center_cache[city] = (lng, lat)
        return lng, lat

    params = {"key": AMAP_KEY, "address": city, "city": city}
    report_progress(f"正在定位 {city} 市中心…")

    data = httpx.get(GEO_URL, params=params, timeout=15).json()
    geocodes = data.get("geocodes") or []
    if not geocodes:
        raise RuntimeError(f"高德地图定位失败：{city}")
    location = geocodes[0]["location"]
    lng, lat = map(float, location.split(","))
    _center_cache[city] = (lng, lat)
    cache_service.set_cached(
        "amap",
        f"center:{city}",
        [lng, lat],
        ttl_seconds=CENTER_CACHE_TTL_SECONDS,
    )
    return lng, lat
def _coordinate_distance(origin: str, destination: str) -> float:
    lng1, lat1 = map(float, origin.split(","))
    lng2, lat2 = map(float, destination.split(","))
    radius = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _distance_meters(city: str, location: str) -> float:
    lng, lat = map(float, location.split(","))
    clng, clat = _city_center(city)
    radius = 6371000
    p1 = math.radians(clat)
    p2 = math.radians(lat)
    dlat = math.radians(lat - clat)
    dlng = math.radians(lng - clng)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _search_pois(city: str, keywords: str, types: str = "", limit: int = 5) -> list[dict]:
    cache_key = (city, keywords, types, limit)
    if cache_key in _poi_cache:
        return list(_poi_cache[cache_key])

    persistent_key = f"poi:{city}|{keywords}|{types}|{limit}"
    cached = cache_service.get_cached("amap", persistent_key)
    if cached is not None:
        _poi_cache[cache_key] = cached
        return list(cached)

    report_progress(f"正在搜索：{keywords}…")

    with _amap_lock:
        for attempt in range(3):
            params = {
                "key": AMAP_KEY,
                "city": city,
                "citylimit": "true",
                "keywords": keywords,
                "offset": str(min(limit, 25)),
                "page": "1",
                "extensions": "base",
            }
            if types:
                params["types"] = types

            response = httpx.get(AMAP_URL, params=params, timeout=15)
            data = response.json()

            if data.get("status") == "1":
                pois = data.get("pois", [])
                _poi_cache[cache_key] = pois
                cache_service.set_cached(
                    "amap",
                    persistent_key,
                    pois,
                    ttl_seconds=POI_CACHE_TTL_SECONDS,
                )
                return pois

            info = data.get("info", "")
            if "LIMIT" in info or "QPS" in info.upper() or "CUQPS" in info:
                time.sleep(1)
                continue

            raise RuntimeError(f"高德地图搜索失败：{info}")

    raise RuntimeError("高德地图请求过于频繁，请稍后重试")


def _is_attraction(poi: dict) -> bool:
    poi_type = poi.get("type", "")
    if any(hint in poi_type for hint in SKIP_TYPE_HINTS):
        return False
    return any(hint in poi_type for hint in ATTRACTION_TYPE_HINTS)


WECHAT_ATTRACTIONS = {
    "故宫博物院",
    "成都大熊猫繁育研究基地",
    "上海迪士尼度假区",
    "北京环球度假区",
    "秦始皇兵马俑博物馆",
    "莫高窟",
    "九寨沟",
    "黄山风景区",
    "张家界国家森林公园",
    "西湖风景名胜区",
    "泰山风景区",
    "长隆野生动物世界",
    "广州塔",
    "东方明珠",
    "布达拉宫",
    "大唐不夜城",
    "洪崖洞",
    "宽窄巷子",
    "武侯祠",
    "锦里",
}

def _booking_key(name: str) -> str:
    return re.sub(r"\s+", "", name or "").lower()


def build_booking_url(name: str) -> str:
    key = _booking_key(name)
    if key in {_booking_key(item) for item in WECHAT_ATTRACTIONS}:
        keyword = quote(f"{name} 官方公众号")
        return f"https://weixin.sogou.com/weixin?type=1&query={keyword}"
    keyword = quote(f"{name} 门票")
    return f"https://piao.ctrip.com/search?keyword={keyword}"


def build_booking_label(name: str) -> str:
    key = _booking_key(name)
    if key in {_booking_key(item) for item in WECHAT_ATTRACTIONS}:
        return "公众号预约"
    return "购票 / 预约"

def _to_attraction(poi: dict) -> AttractionCandidate:
    poi_type = poi.get("type", "")
    name = poi.get("name", "")
    return AttractionCandidate(
        name=name,
        address=poi.get("address", ""),
        duration="2小时",
        description="",
        category=poi_type.split(";")[-1] if poi_type else "",
        recommended_time="",
        location=poi.get("location", ""),
        booking_url=build_booking_url(name),
        booking_label=build_booking_label(name),
    )


def _to_food(poi: dict) -> FoodCandidate:
    poi_type = poi.get("type", "")
    return FoodCandidate(
        name=poi.get("name", ""),
        cuisine=poi_type.split(";")[-1] if poi_type else "",
        price_range="",
        address=poi.get("address", ""),
        description="",
        best_time="",
        location=poi.get("location", ""),
    )


def search_attractions(req: TripRequest, keywords: list[str], limit: int = 8) -> list[AttractionCandidate]:
    results: list[AttractionCandidate] = []
    seen: set[str] = set()

    for keyword in keywords[:4]:
        pois = _search_pois(req.destination, keyword, types="", limit=4)

        for poi in pois:
            location = poi.get("location", "")
            if not location:
                continue
            if _distance_meters(req.destination, location) > 40000:
                continue
            if not _is_attraction(poi):
                continue

            name = poi.get("name", "")
            if name in seen:
                continue
            seen.add(name)
            results.append(_to_attraction(poi))

            if len(results) >= limit:
                return results

    if len(results) < limit:
        fallback = _search_pois(req.destination, req.destination + "景点", types="110100", limit=10)
        for poi in fallback:
            location = poi.get("location", "")
            if not location:
                continue
            if _distance_meters(req.destination, location) > 40000:
                continue
            if not _is_attraction(poi):
                continue

            name = poi.get("name", "")
            if name in seen:
                continue
            seen.add(name)
            results.append(_to_attraction(poi))

            if len(results) >= limit:
                break

    return results


def search_foods(req: TripRequest, keywords: list[str], limit: int = 8) -> list[FoodCandidate]:
    results: list[FoodCandidate] = []
    seen: set[str] = set()

    for keyword in keywords[:4]:
        pois = _search_pois(req.destination, keyword, types="050000", limit=4)

        for poi in pois:
            location = poi.get("location", "")
            if not location:
                continue
            if _distance_meters(req.destination, location) > 25000:
                continue

            poi_type = poi.get("type", "")
            if "餐饮服务" not in poi_type or "住宿服务" in poi_type:
                continue

            name = poi.get("name", "")
            if name in seen:
                continue
            seen.add(name)
            results.append(_to_food(poi))

            if len(results) >= limit:
                return results

    if len(results) < limit:
        fallback = _search_pois(req.destination, req.destination + "小吃", types="050100", limit=10)
        for poi in fallback:
            location = poi.get("location", "")
            if not location:
                continue
            if _distance_meters(req.destination, location) > 25000:
                continue

            poi_type = poi.get("type", "")
            if "餐饮服务" not in poi_type or "住宿服务" in poi_type:
                continue

            name = poi.get("name", "")
            if name in seen:
                continue
            seen.add(name)
            results.append(_to_food(poi))

            if len(results) >= limit:
                break

    return results


def _format_phone(phone) -> str:
    if isinstance(phone, list):
        return ";".join(str(item) for item in phone if item)
    return str(phone or "")


def search_hotels(req: TripRequest, limit: int = 6) -> list[HotelCandidate]:
    pois = _search_pois(
        city=req.destination,
        keywords=req.destination,
        types="100000",
        limit=limit,
    )

    results: list[HotelCandidate] = []
    seen: set[str] = set()

    for poi in pois:
        location = poi.get("location", "")
        if not location:
            continue
        if _distance_meters(req.destination, location) > 40000:
            continue

        poi_type = poi.get("type", "")
        if "住宿服务" not in poi_type:
            continue

        name = poi.get("name", "")
        if name in seen:
            continue
        seen.add(name)

        price_hint = ""
        if req.hotel_budget:
            price_hint = f"预算参考：{req.hotel_budget}元/晚"

        results.append(
            HotelCandidate(
                name=name,
                address=poi.get("address", ""),
                location=location,
                category=poi_type.split(";")[-1] if poi_type else "",
                phone=_format_phone(poi.get("tel")),
                price_hint=price_hint,
            )
        )

        if len(results) >= limit:
            break

    return results

def _parse_int(text: str) -> int:
    try:
        return int(float(text or 0))
    except (TypeError, ValueError):
        return 0


def _wind_direction_text(degrees: int) -> str:
    directions = ["北风", "东北风", "东风", "东南风", "南风", "西南风", "西风", "西北风"]
    return directions[int(((degrees % 360) + 22.5) // 45) % 8]


def _wind_power_text(speed_kmh: int) -> str:
    if speed_kmh < 6:
        return "1-2级"
    if speed_kmh < 12:
        return "2-3级"
    if speed_kmh < 20:
        return "3-4级"
    if speed_kmh < 29:
        return "4-5级"
    if speed_kmh < 39:
        return "5-6级"
    return "6级以上"


def _weather_suggestion(
    day_weather: str,
    night_weather: str,
    temp_min: int,
    temp_max: int,
    precipitation_probability: int,
) -> str:
    texts: list[str] = []
    weather_text = f"{day_weather}{night_weather}"
    if any(key in weather_text for key in ("雨", "雷", "雪")):
        texts.append("有雨雪天气，建议备好雨具，优先安排室内备选")
    if precipitation_probability >= 60:
        texts.append("降水概率较高，行程可预留弹性")
    if temp_max >= 33:
        texts.append("高温日，注意防暑补水")
    if temp_min <= 5:
        texts.append("低温日，早晚注意保暖")
    if temp_max - temp_min >= 12:
        texts.append("昼夜温差大，建议洋葱式穿衣")
    return "；".join(texts) if texts else "天气整体平稳，适合按计划出行"


_WMO_WEATHER = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "毛毛雨",
    56: "冻毛毛雨",
    57: "冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷雨",
    96: "雷雨伴冰雹",
    99: "强雷雨伴冰雹",
}


def _open_meteo_forecast(city: str) -> list[WeatherForecast]:
    lng, lat = _city_center(city)
    response = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lng,
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,wind_speed_10m_max,"
                "wind_direction_10m_dominant"
            ),
            "timezone": "auto",
            "forecast_days": 7,
        },
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    codes = daily.get("weather_code") or []
    temp_maxes = daily.get("temperature_2m_max") or []
    temp_mins = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_probability_max") or []
    wind_speeds = daily.get("wind_speed_10m_max") or []
    wind_dirs = daily.get("wind_direction_10m_dominant") or []
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    forecasts: list[WeatherForecast] = []
    for index, date_text in enumerate(dates):
        try:
            parsed = date.fromisoformat(date_text)
        except ValueError:
            continue
        code = int(codes[index]) if index < len(codes) else 0
        weather_text = _WMO_WEATHER.get(code, "未知")
        temp_min = _parse_int(temp_mins[index]) if index < len(temp_mins) else 0
        temp_max = _parse_int(temp_maxes[index]) if index < len(temp_maxes) else 0
        precip_value = _parse_int(precip[index]) if index < len(precip) else 0
        wind_speed = _parse_int(wind_speeds[index]) if index < len(wind_speeds) else 0
        wind_dir = _parse_int(wind_dirs[index]) if index < len(wind_dirs) else 0
        forecasts.append(
            WeatherForecast(
                date=date_text,
                week=weekday_names[parsed.weekday()],
                day_weather=weather_text,
                night_weather=weather_text,
                temp_min=temp_min,
                temp_max=temp_max,
                wind_direction=_wind_direction_text(wind_dir),
                wind_power=_wind_power_text(wind_speed),
                precipitation_probability=precip_value,
                suggestion=_weather_suggestion(
                    weather_text,
                    weather_text,
                    temp_min,
                    temp_max,
                    precip_value,
                ),
            )
        )
    return forecasts


def _amap_forecast(city: str) -> list[WeatherForecast]:
    params = {
        "key": AMAP_KEY,
        "city": city,
        "extensions": "all",
    }
    response = httpx.get(WEATHER_URL, params=params, timeout=15)
    data = response.json()
    if data.get("status") != "1":
        return []
    forecasts_data = data.get("forecasts") or []
    if not forecasts_data:
        return []
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    forecasts: list[WeatherForecast] = []
    for cast in forecasts_data[0].get("casts") or []:
        date_text = cast.get("date", "")
        try:
            parsed = date.fromisoformat(date_text)
        except ValueError:
            parsed = None
        day_weather = cast.get("dayweather", "")
        night_weather = cast.get("nightweather", "")
        temp_min = _parse_int(cast.get("nighttemp"))
        temp_max = _parse_int(cast.get("daytemp"))
        forecasts.append(
            WeatherForecast(
                date=date_text,
                week=weekday_names[parsed.weekday()] if parsed else "",
                day_weather=day_weather,
                night_weather=night_weather,
                temp_min=temp_min,
                temp_max=temp_max,
                wind_direction=cast.get("daywind", ""),
                wind_power=cast.get("daypower", ""),
                precipitation_probability=0,
                suggestion=_weather_suggestion(
                    day_weather,
                    night_weather,
                    temp_min,
                    temp_max,
                    0,
                ),
            )
        )
    return forecasts


def get_weather_forecast(city: str) -> list[WeatherForecast]:
    persistent_key = f"forecast:{city}"
    cached = cache_service.get_cached("amap", persistent_key)
    if cached is not None:
        return [WeatherForecast.model_validate(item) for item in cached]

    try:
        report_progress(f"正在获取 {city} 未来 7 天预报…")

        forecasts = _open_meteo_forecast(city)
        if forecasts:
            cache_service.set_cached(
                "amap",
                persistent_key,
                [forecast.model_dump() for forecast in forecasts],
                ttl_seconds=WEATHER_CACHE_TTL_SECONDS,
            )
            return forecasts
    except Exception:
        pass

    try:
        forecasts = _amap_forecast(city)
        if forecasts:
            cache_service.set_cached(
                "amap",
                persistent_key,
                [forecast.model_dump() for forecast in forecasts],
                ttl_seconds=WEATHER_CACHE_TTL_SECONDS,
            )
        return forecasts
    except Exception:
        return []
def get_weather(city: str, travel_date: str = "") -> WeatherInfo:
    persistent_key = f"weather:{city}|{travel_date}"
    cached = cache_service.get_cached("amap", persistent_key)
    if cached is not None:
        return WeatherInfo.model_validate(cached)

    params = {
        "key": AMAP_KEY,
        "city": city,
        "extensions": "base",
    }

    report_progress(f"正在获取 {city} 今日天气…")

    response = httpx.get(WEATHER_URL, params=params, timeout=15)
    data = response.json()

    if data.get("status") != "1":
        raise RuntimeError(f"高德地图天气查询失败：{data.get('info')}")

    lives = data.get("lives") or []
    if not lives:
        return WeatherInfo(city=city)

    live = lives[0]
    info = WeatherInfo(
        city=live.get("city", city),
        weather=live.get("weather", ""),
        temperature=live.get("temperature", ""),
        wind_direction=live.get("winddirection", ""),
        wind_power=live.get("windpower", ""),
        humidity=live.get("humidity", ""),
        report_time=live.get("reporttime", ""),
        travel_date=travel_date,
    )
    cache_service.set_cached(
        "amap",
        persistent_key,
        info.model_dump(),
        ttl_seconds=WEATHER_CACHE_TTL_SECONDS,
    )
    return info
def _format_seconds(seconds: int) -> str:
    minutes = max(1, round(seconds / 60))
    if minutes < 60:
        return f"约{minutes}分钟"
    hours = minutes // 60
    mins = minutes % 60
    if mins:
        return f"约{hours}小时{mins}分钟"
    return f"约{hours}小时"


def _format_distance(meters: int) -> str:
    if meters >= 1000:
        return f"{meters / 1000:.1f}公里"
    return f"{meters}米"


def _pick_route_mode(origin: str, destination: str, mode: str) -> str:
    if mode in ("walking", "driving", "transit", "bicycling"):
        return mode
    distance = _coordinate_distance(origin, destination)
    if distance <= 1500:
        return "walking"
    if distance <= 8000:
        return "driving"
    return "transit"


def _amap_route_request(url: str, params: dict) -> dict:
    for attempt in range(3):
        response = httpx.get(url, params=params, timeout=20)
        data = response.json()
        if data.get("status") == "1":
            return data

        info = data.get("info", "")
        if "LIMIT" in info or "QPS" in info.upper() or "CUQPS" in info:
            time.sleep(1)
            continue

        raise RuntimeError(f"高德地图路线查询失败：{info}")

    raise RuntimeError("高德地图路线请求过于频繁，请稍后重试")


def _route_polyline(path: dict) -> str:
    lines = []
    for step in path.get("steps") or []:
        line = step.get("polyline", "")
        if line:
            lines.append(line)
    return ";".join(lines)


def _transit_polyline(transit: dict) -> str:
    lines = []
    for segment in transit.get("segments") or []:
        walking = segment.get("walking") or {}
        for step in walking.get("steps") or []:
            line = step.get("polyline", "")
            if line:
                lines.append(line)
        bus = segment.get("bus") or {}
        for busline in bus.get("buslines") or []:
            line = busline.get("polyline", "")
            if line:
                lines.append(line)
        railway = segment.get("railway") or {}
        trip = railway.get("trip") or {}
        line = trip.get("polyline", "")
        if line:
            lines.append(line)
    return ";".join(lines)


def _fetch_route(origin: str, destination: str, mode: str, city: str = "") -> RouteInfo:
    params = {
        "key": AMAP_KEY,
        "origin": origin,
        "destination": destination,
        "extensions": "base",
    }

    url = ROUTE_URL
    if mode == "walking":
        url = WALKING_URL
    elif mode == "bicycling":
        url = BICYCLING_URL
    elif mode == "transit":
        url = TRANSIT_URL
        params["city"] = city or "全国"
        params["cityd"] = city or "全国"
    else:
        params["strategy"] = "10"

    data = _amap_route_request(url, params)

    if mode == "transit":
        transits = data.get("route", {}).get("transits") or []
        if not transits:
            raise RuntimeError("高德地图暂未找到合适的公交路线")
        transit = transits[0]
        duration = int(transit.get("duration", 0) or 0)
        distance = int(transit.get("distance", 0) or 0)
        polyline = _transit_polyline(transit)
    else:
        paths = data.get("route", {}).get("paths") or []
        if not paths:
            raise RuntimeError("高德地图暂未找到合适的路线")
        path = paths[0]
        duration = int(path.get("duration", 0) or 0)
        distance = int(path.get("distance", 0) or 0)
        polyline = _route_polyline(path)

    return RouteInfo(
        mode=mode,
        duration_seconds=duration,
        distance_meters=distance,
        duration_text=_format_seconds(duration),
        distance_text=_format_distance(distance),
        polyline=polyline,
    )


def get_route(origin: str, destination: str, mode: str = "auto", city: str = "") -> RouteInfo:
    resolved_mode = _pick_route_mode(origin, destination, mode)
    cache_key = (origin, destination, resolved_mode, city)
    if cache_key in _route_cache:
        return _route_cache[cache_key].model_copy(deep=True)

    persistent_key = f"route:{origin}|{destination}|{resolved_mode}|{city}"
    cached = cache_service.get_cached("amap", persistent_key)
    if cached is not None:
        try:
            route = RouteInfo.model_validate(cached)
            _route_cache[cache_key] = route
            return route.model_copy(deep=True)
        except Exception:
            pass

    try:
        report_progress(f"正在规划路线：{origin} → {destination}…")

        route = _fetch_route(origin, destination, resolved_mode, city)
    except Exception:
        if resolved_mode == "driving":
            route = RouteInfo(mode="driving")
        else:
            try:
                route = _fetch_route(origin, destination, "driving", city)
            except Exception:
                route = RouteInfo(mode="driving")

    _route_cache[cache_key] = route
    if route.mode == resolved_mode and (
        route.duration_seconds or route.distance_meters or route.polyline
    ):
        cache_service.set_cached(
            "amap",
            persistent_key,
            route.model_dump(),
            ttl_seconds=ROUTE_CACHE_TTL_SECONDS,
        )
    return route.model_copy(deep=True)
def get_route_time(origin: str, destination: str) -> RouteInfo:
    return get_route(origin, destination, "driving")


def _ordered_day_stops(day: DayPlan) -> list[tuple[str, str, str]]:
    stops: list[tuple[str, str, str]] = []
    max_len = max(len(day.spots), len(day.foods))
    for index in range(max_len):
        if index < len(day.spots):
            spot = day.spots[index]
            if spot.location:
                stops.append((spot.name, spot.location, "spot"))
        if index < len(day.foods):
            food = day.foods[index]
            if food.location:
                stops.append((food.name, food.location, "food"))
    return stops


def build_route_legs(
    plan: TripPlan,
    hotel: HotelCandidate | None,
    transport_mode: str = "auto",
) -> list[RouteInfo]:
    legs: list[RouteInfo] = []
    for day in plan.daily_plans:
        stops = _ordered_day_stops(day)
        if not stops:
            continue

        if hotel is not None and hotel.location:
            anchor_name = hotel.name or "酒店"
            anchor_location = hotel.location
        else:
            anchor_name, anchor_location, _ = stops[0]
            stops = stops[1:]

        if not stops:
            continue

        previous_name = anchor_name
        previous_location = anchor_location

        for name, location, stop_type in stops:
            report_progress(f"正在规划路线：{previous_name} → {name}…")
            route = get_route(
                previous_location,
                location,
                mode=transport_mode,
                city=plan.destination,
            )
            route.leg_key = f"d{day.day}:{previous_name}->{name}"
            route.from_name = previous_name
            route.to_name = name
            route.from_location = previous_location
            route.to_location = location
            route.day = day.day
            route.stop_type = stop_type
            legs.append(route)

            previous_name = name
            previous_location = location

        report_progress(f"正在规划返程路线：{previous_name} → {anchor_name}…")
        return_route = get_route(
            previous_location,
            anchor_location,
            mode=transport_mode,
            city=plan.destination,
        )
        return_route.leg_key = f"d{day.day}:{previous_name}->{anchor_name}"
        return_route.from_name = previous_name
        return_route.to_name = anchor_name
        return_route.from_location = previous_location
        return_route.to_location = anchor_location
        return_route.day = day.day
        return_route.stop_type = "hotel"
        legs.append(return_route)

    return legs


def search_nearby_pois(
    location: str,
    types: str = "",
    keywords: str = "",
    radius: int = 3000,
    limit: int = 6,
) -> list[NearbyPoi]:
    persistent_key = f"nearby:{location}|{types}|{keywords}|{radius}|{limit}"
    cached = cache_service.get_cached("amap", persistent_key)
    if cached is not None:
        pois = cached
    else:
        params = {
            "key": AMAP_KEY,
            "location": location,
            "radius": str(radius),
            "offset": str(limit),
            "page": "1",
            "sortrule": "distance",
            "extensions": "base",
        }
        if types:
            params["types"] = types
        if keywords:
            params["keywords"] = keywords

        report_progress("正在搜索酒店周边设施…")

        response = httpx.get(AROUND_URL, params=params, timeout=15)
        data = response.json()

        if data.get("status") != "1":
            raise RuntimeError(f"高德地图周边搜索失败：{data.get('info')}")

        pois = data.get("pois", [])
        cache_service.set_cached(
            "amap",
            persistent_key,
            pois,
            ttl_seconds=POI_CACHE_TTL_SECONDS,
        )

    results = []

    for poi in pois:
        poi_type = poi.get("type", "")
        results.append(
            NearbyPoi(
                name=poi.get("name", ""),
                address=poi.get("address", ""),
                location=poi.get("location", ""),
                category=poi_type.split(";")[-1] if poi_type else "",
                distance=poi.get("distance", ""),
            )
        )

    return results
