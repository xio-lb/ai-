from app.agents.orchestrator import plan_trip
from app.schemas.trip import TripRequest

req = TripRequest(
    destination="成都",
    days=3,
    budget=3000,
    preferences=["美食", "人文"],
)

plan = plan_trip(req)
print(plan.model_dump_json(indent=2, ensure_ascii=False))