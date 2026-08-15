from app.services.amap_client import get_route_time, search_nearby_pois

hotel_location = "104.053004,30.646796"
spot_location = "104.056100,30.648228"

route = get_route_time(hotel_location, spot_location)
print("驾车路线：", route.duration_text, route.distance_text)

nearby = search_nearby_pois(
    hotel_location,
    types="110100",
    radius=3000,
    limit=5,
)

print("周边景点：")
for item in nearby:
    print(f"{item.name} | {item.category} | {item.distance}米 | {item.location}")
print("路线点数：", len(route.polyline.split(";")) if route.polyline else 0)
