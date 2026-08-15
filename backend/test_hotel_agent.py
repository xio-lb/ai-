from app.agents.hotel_agent import recommend_hotels
from app.schemas.trip import TripRequest

req = TripRequest(
    destination="成都",
    days=3,
    budget=3000,
    preferences=["美食", "人文"],
    hotel_budget=400,
)

hotels = recommend_hotels(req, count=6)

for item in hotels:
    print(f"{item.name} | {item.category} | {item.phone} | {item.price_hint} | {item.location}")