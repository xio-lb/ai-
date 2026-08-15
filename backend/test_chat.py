from app.agents.chat_agent import chat_requirement

messages = [
    {"role": "user", "content": "我想去成都玩"},
]

result = chat_requirement(messages)
print("回复：", result["reply"])
print("ready：", result["ready"])
print("还缺：", result.get("missing"))

messages.append({"role": "assistant", "content": result["reply"]})
messages.append({
    "role": "user",
    "content": "3天，预算3000，从北京出发，2026-09-20，节奏轻松，偏好美食和人文",
})

result2 = chat_requirement(messages)
print("回复2：", result2["reply"])
print("ready2：", result2["ready"])

if result2.get("trip_request"):
    print("行程请求：", result2["trip_request"])