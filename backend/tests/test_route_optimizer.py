from app.schemas.trip import DayPlan, FoodCandidate, Spot, TripPlan
from app.services.route_optimizer import (
    haversine_meters,
    optimize_plan_days,
    parse_location,
    path_length_meters,
    two_opt_order,
)


def _spot(name: str, location: str) -> Spot:
    return Spot(name=name, location=location, duration="1小时")


def _food(name: str, location: str) -> FoodCandidate:
    return FoodCandidate(name=name, location=location)


def test_parse_location_rejects_out_of_range():
    assert parse_location("104.05,30.66") == (104.05, 30.66)
    assert parse_location("") is None
    assert parse_location("abc") is None
    assert parse_location("0,0") is None
    assert parse_location("200,30") is None


def test_haversine_known_distance():
    # ~1.4 km between two points 0.01 degrees apart in Chengdu.
    distance = haversine_meters((104.05, 30.66), (104.06, 30.67))
    assert 1400 < distance < 1550


def test_two_opt_untangles_a_crossing():
    points = [(0.0, 0.0), (1.0, 1.0), (0.0, 1.0), (1.0, 0.0)]
    order = two_opt_order(points, [0, 1, 2, 3])
    assert order[0] == 0
    assert path_length_meters([points[i] for i in order]) <= path_length_meters([points[i] for i in [0, 1, 2, 3]])


def test_optimizer_reorders_zigzag_day():
    day = DayPlan(
        day=1,
        theme="测试",
        spots=[
            _spot("A", "104.00,30.00"),
            _spot("B", "104.30,30.00"),
            _spot("C", "104.10,30.00"),
        ],
        foods=[_food("F", "104.40,30.00")],
    )
    plan = TripPlan(destination="测试", days=1, budget=1000, daily_plans=[day])

    results = optimize_plan_days(plan)

    assert results[0].changed is True
    assert results[0].distance_after_meters < results[0].distance_before_meters
    assert plan.daily_plans[0].spots[0].name == "A"
    assert [spot.name for spot in plan.daily_plans[0].spots] == ["A", "C", "B"]
    assert [food.name for food in plan.daily_plans[0].foods] == ["F"]


def test_optimizer_keeps_order_when_already_short():
    day = DayPlan(
        day=1,
        theme="测试",
        spots=[
            _spot("A", "104.00,30.00"),
            _spot("B", "104.01,30.00"),
            _spot("C", "104.02,30.00"),
        ],
        foods=[],
    )
    plan = TripPlan(destination="测试", days=1, budget=1000, daily_plans=[day])
    results = optimize_plan_days(plan)
    assert results[0].changed is False
    assert [spot.name for spot in plan.daily_plans[0].spots] == ["A", "B", "C"]


def test_optimizer_skips_days_without_enough_coordinates():
    day = DayPlan(day=1, theme="测试", spots=[_spot("A", ""), _spot("B", "104.01,30.00")], foods=[])
    plan = TripPlan(destination="测试", days=1, budget=1000, daily_plans=[day])
    results = optimize_plan_days(plan)
    assert results[0].changed is False
