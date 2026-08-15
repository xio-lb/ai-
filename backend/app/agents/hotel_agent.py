from app.schemas.trip import HotelCandidate, TripRequest
from app.services.amap_client import search_hotels


def recommend_hotels(req: TripRequest, count: int = 6) -> list[HotelCandidate]:
    return search_hotels(req, limit=count)