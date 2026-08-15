from app.agents.weather_agent import fetch_weather

info = fetch_weather("成都")

print(f"城市：{info.city}")
print(f"天气：{info.weather}")
print(f"温度：{info.temperature}℃")
print(f"风向：{info.wind_direction}")
print(f"风力：{info.wind_power}")
print(f"湿度：{info.humidity}%")
print(f"更新时间：{info.report_time}")