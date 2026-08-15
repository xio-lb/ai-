from app.schemas.trip import DayPlan, RouteInfo, Spot, TripPlan
from app.services import history_migration


def _old_plan():
    return TripPlan(
        destination="TestCity",
        days=1,
        budget=1000,
        daily_plans=[
            DayPlan(
                day=1,
                theme="City",
                spots=[
                    Spot(name="Attraction A", location="1,1"),
                    Spot(name="Attraction B", location="2,2"),
                ],
                foods=[],
            )
        ],
        total_cost=500,
    )


def test_migrate_plan_rebuilds_missing_routes(monkeypatch):
    plan = _old_plan()
    fake_legs = [
        RouteInfo(
            mode="driving",
            day=1,
            from_name="Attraction A",
            to_name="Attraction B",
            stop_type="spot",
            duration_seconds=60,
            distance_meters=100,
            polyline="1,1;2,2",
        )
    ]
    monkeypatch.setattr(
        history_migration,
        "build_route_legs",
        lambda plan, hotel, mode: fake_legs,
    )
    migrated = history_migration.migrate_plan(plan)
    assert migrated.route_legs == fake_legs
    assert migrated.routes["Attraction B"].to_name == "Attraction B"
    assert migrated.transport_mode == "auto"


def test_migrate_plan_derives_hotel_from_return_leg():
    plan = _old_plan()
    plan.route_legs = [
        RouteInfo(
            mode="driving",
            day=1,
            from_name="Attraction B",
            to_name="City Hotel",
            to_location="0,0",
            stop_type="hotel",
        )
    ]
    migrated = history_migration.migrate_plan(plan)
    assert migrated.hotels
    assert migrated.hotels[0].name == "City Hotel"
    assert migrated.routes["City Hotel"].to_name == "City Hotel"
