from app.schemas.trip import DayPlan, HotelCandidate, RouteInfo, Spot, TripPlan
from app.services import amap_client
from app.services import cache_service


def test_get_route_falls_back_to_driving(monkeypatch, tmp_path):
    def fail(origin, destination, mode, city=""):
        raise RuntimeError("network down")

    monkeypatch.setattr(cache_service, "DB_PATH", tmp_path / "cache.db")
    cache_service.init_db()
    monkeypatch.setattr(amap_client, "_fetch_route", fail)
    monkeypatch.setattr(amap_client, "_route_cache", {})
    route = amap_client.get_route(
        "116.40,39.90",
        "116.41,39.91",
        mode="walking",
        city="北京",
    )
    assert route.mode == "driving"


def test_build_route_legs_closes_loop(monkeypatch):
    def fake_route(origin, destination, mode="auto", city=""):
        return RouteInfo(
            mode=mode,
            duration_seconds=60,
            distance_meters=100,
            duration_text="1分钟",
            distance_text="100米",
            polyline=f"{origin};{destination}",
        )

    monkeypatch.setattr(amap_client, "get_route", fake_route)
    plan = TripPlan(
        destination="成都",
        days=1,
        budget=1000,
        daily_plans=[
            DayPlan(
                day=1,
                theme="市区",
                spots=[
                    Spot(name="宽窄巷子", location="104.06,30.67"),
                    Spot(name="锦里", location="104.07,30.66"),
                ],
                foods=[],
            )
        ],
    )
    hotel = HotelCandidate(name="成都酒店", location="104.05,30.65")
    legs = amap_client.build_route_legs(plan, hotel, "walking")
    assert legs[0].from_name == hotel.name
    assert legs[-1].stop_type == "hotel"
    assert legs[-1].to_name == hotel.name