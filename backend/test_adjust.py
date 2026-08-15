from app.agents.orchestrator import adjust_trip, plan_trip
from app.schemas.trip import TripRequest

req = TripRequest(
    destination="成都",
    days=2,
    budget=2500,
    preferences=["美食", "人文"],
)

current_plan = plan_trip(req)
print("=== 当前行程 ===")
print(current_plan.model_dump_json(indent=2, ensure_ascii=False))

adjusted_plan = adjust_trip(current_plan, "把第二天的餐厅换成更便宜的")
print("=== 调整后行程 ===")
print(adjusted_plan.model_dump_json(indent=2, ensure_ascii=False))