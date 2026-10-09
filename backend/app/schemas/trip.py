from typing import Any

from pydantic import BaseModel


class Spot(BaseModel):
    name: str
    address: str = ""
    duration: str = "2小时"
    description: str = ""
    location: str = ""
    booking_url: str = ""
    booking_label: str = ""


class FoodCandidate(BaseModel):
    name: str
    cuisine: str = ""
    price_range: str = ""
    address: str = ""
    description: str = ""
    best_time: str = ""
    location: str = ""

class HotelCandidate(BaseModel):
    name: str
    address: str = ""
    location: str = ""
    category: str = ""
    phone: str = ""
    price_hint: str = ""

class WeatherForecast(BaseModel):
    date: str = ""
    week: str = ""
    day_weather: str = ""
    night_weather: str = ""
    temp_min: int = 0
    temp_max: int = 0
    wind_direction: str = ""
    wind_power: str = ""
    precipitation_probability: int = 0
    suggestion: str = ""

class WeatherInfo(BaseModel):
    city: str = ""
    weather: str = ""
    temperature: str = ""
    wind_direction: str = ""
    wind_power: str = ""
    humidity: str = ""
    report_time: str = ""
    travel_date: str = ""
    forecasts: list[WeatherForecast] = []

class RouteInfo(BaseModel):
    mode: str = "driving"
    duration_seconds: int = 0
    distance_meters: int = 0
    duration_text: str = ""
    distance_text: str = ""
    polyline: str = ""
    leg_key: str = ""
    from_name: str = ""
    to_name: str = ""
    from_location: str = ""
    to_location: str = ""
    day: int = 0
    stop_type: str = ""


class NearbyPoi(BaseModel):
    name: str
    address: str = ""
    location: str = ""
    category: str = ""
    distance: str = ""

class DayPlan(BaseModel):
    day: int
    theme: str
    spots: list[Spot] = []
    foods: list[FoodCandidate] = []


class BudgetCategoryItem(BaseModel):
    name: str
    amount: int = 0


class BudgetCategoryDetail(BaseModel):
    category: str
    amount: int = 0
    min_amount: int = 0
    max_amount: int = 0
    typical: int = 0
    note: str = ""
    items: list[BudgetCategoryItem] = []


class BudgetDayDetail(BaseModel):
    day: int
    amount: int = 0
    min_amount: int = 0
    max_amount: int = 0
    typical: int = 0
    categories: dict[str, int] = {}


class ActualExpense(BaseModel):
    day: int = 0
    category: str = ""
    amount: int | None = None
    note: str = ""


class BudgetDetail(BaseModel):
    total_cost: int = 0
    budget: int = 0
    days: list[BudgetDayDetail] = []
    categories: list[BudgetCategoryDetail] = []
    actual_expenses: list[ActualExpense] = []


class BudgetReport(BaseModel):
    budget: int
    total_cost: int
    within_budget: bool
    savings: int
    suggestions: list[str] = []


class TripPlan(BaseModel):
    destination: str
    days: int
    budget: int
    preferences: list[str] = []
    user_preferences: list[str] = []
    variant_label: str = ""
    variant_pace: str = ""
    variant_theme: str = ""
    departure_city: str = ""
    dietary_notes: str = ""
    hotel_budget: int = 0
    companions: int = 1
    overview: str = ""
    daily_plans: list[DayPlan] = []
    total_cost: int = 0
    notes: list[str] = []
    budget_report: BudgetReport | None = None
    budget_detail: BudgetDetail | None = None
    user_memory: dict[str, Any] = {}
    spending_profile: dict[str, Any] = {}
    quality_report: dict[str, Any] = {}
    hotels: list[HotelCandidate] = []
    weather: WeatherInfo | None = None
    nearby: list[NearbyPoi] = []
    routes: dict[str, RouteInfo] = {}
    route_legs: list[RouteInfo] = []
    route_optimization: list[dict[str, Any]] = []
    transport_mode: str = "auto"


class TripRequest(BaseModel):
    destination: str
    days: int
    budget: int
    preferences: list[str] = []
    departure_city: str = ""
    travel_date: str = ""
    pace: str = "standard"
    variant_theme: str = ""
    hotel_budget: int = 0
    dietary_notes: str = ""
    companions: int = 1
    transport_mode: str = "auto"


class AttractionCandidate(BaseModel):
    name: str
    address: str = ""
    duration: str = "2小时"
    description: str = ""
    category: str = ""
    recommended_time: str = ""
    location: str = ""
    booking_url: str = ""
    booking_label: str = ""
