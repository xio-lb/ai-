from app.agents.food_agent import recommend_foods
from app.agents.requirement_agent import analyze_requirement
from app.schemas.trip import TripRequest

req = TripRequest(
    destination="成都",
    days=3,
    budget=3000,
    preferences=["美食", "人文"],
)

requirement = analyze_requirement(req)
foods = recommend_foods(req, requirement, count=6)

for item in foods:
    print(f"{item.name} | {item.cuisine} | {item.price_range} | {item.location}")