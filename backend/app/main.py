import json
import queue
import threading

from fastapi import FastAPI
from fastapi import HTTPException, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.agents.graph import trip_graph
from app.agents.orchestrator import (
    build_variant_plan,
    pick_variant_themes,
    plan_trip,
    plan_variants,
)
from app.schemas.trip import TripRequest
from pydantic import BaseModel
from app.agents.orchestrator import adjust_trip, plan_trip
from app.schemas.trip import TripPlan, TripRequest
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.services.history_service import delete_plan, get_plan, init_db, list_plans, save_plan
from app.services import chat_service, observability
from app.services.memory_service import (
    get_user_memory,
    merge_memory_into_request,
    save_user_memory,
    update_memory_from_plan,
)
from app.agents.chat_agent import chat_requirement
from app.services.amap_client import build_route_legs
from app.services.observability import trace_generation
from app.services.progress import reset_progress_callback, set_progress_callback


app = FastAPI(title="AI Travel Planner")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
init_db()
chat_service.init_db()
observability.init_db()

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "请求参数有误，请检查后重试"})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": "请求处理失败，请稍后重试"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": _friendly_error(exc)})



class AdjustRequest(BaseModel):
    current_plan: TripPlan
    user_message: str


class RouteRecalcRequest(BaseModel):
    plan: TripPlan
    transport_mode: str = "auto"


@app.post("/api/trip/plan/adjust")
def adjust_trip_endpoint(req: AdjustRequest):
    plan = adjust_trip(req.current_plan, req.user_message)
    return plan.model_dump()


@app.post("/api/trip/plan/routes")
def recalc_routes_endpoint(req: RouteRecalcRequest):
    plan = req.plan
    hotel = plan.hotels[0] if plan.hotels else None
    legs = build_route_legs(plan, hotel, req.transport_mode)
    plan.route_legs = legs
    plan.transport_mode = req.transport_mode
    plan.routes = {leg.to_name: leg for leg in legs if leg.to_name}
    return plan.model_dump()

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/metrics/summary")
def metrics_summary(days: int = 30):
    return observability.summary(days=max(1, min(days, 365)))


@app.get("/api/metrics/traces")
def metrics_traces(days: int = 30, limit: int = 50, offset: int = 0):
    traces = observability.list_traces(
        days=max(1, min(days, 365)),
        limit=max(1, min(limit, 200)),
        offset=max(0, offset),
    )
    return {"items": traces, "count": len(traces)}


@app.get("/api/metrics/traces/{trace_id}")
def metrics_trace_detail(trace_id: str):
    trace = observability.get_trace(trace_id)
    if trace is None:
        return JSONResponse(status_code=404, content={"detail": "trace not found"})
    return trace


@app.get("/metrics")
def prometheus_metrics(days: int = 30):
    return PlainTextResponse(
        observability.prometheus_text(days=max(1, min(days, 365))),
        media_type="text/plain; version=0.0.4",
    )


@app.post("/api/trip/plan")
def plan_trip_endpoint(req: TripRequest):
    plan = plan_trip(merge_memory_into_request(req))
    return plan.model_dump()


def _friendly_error(exc: Exception) -> str:
    message = str(exc).strip()
    lower = message.lower()
    if "openai" in lower or "deepseek" in lower or "api error" in lower:
        return "AI 服务暂时不可用，请稍后重试"
    if message and ("高德" in message or "行程" in message or "服务" in message):
        return message
    return "服务暂时不可用，请稍后重试"
def _sse_events(events):
    while True:
        item = events.get()
        event_type = item["type"]
        if event_type == "exit":
            break
        if event_type == "progress":
            yield f"event: progress\ndata: {json.dumps({'message': item['message']}, ensure_ascii=False)}\n\n"
        elif event_type == "node":
            yield f"event: node\ndata: {json.dumps({'node': item['node']}, ensure_ascii=False)}\n\n"
        elif event_type == "variant-start":
            yield f"event: variant-start\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
        elif event_type == "variant-done":
            yield f"event: variant-done\ndata: {item['plan'].model_dump_json()}\n\n"
        elif event_type == "done":
            if item.get("plan") is not None:
                yield f"event: done\ndata: {item['plan'].model_dump_json()}\n\n"
            else:
                yield "event: done\ndata: {}\n\n"
        elif event_type == "error":
            yield f"event: error\ndata: {json.dumps({'message': item['message']}, ensure_ascii=False)}\n\n"


def _run_plan_stream(merged, events):
    final_plan = None

    def sink(message):
        events.put({"type": "progress", "message": message})

    with trace_generation(source="api_stream", request=merged) as trace:
        token = set_progress_callback(sink)
        try:
            for step in trip_graph.stream({"request": merged}, stream_mode="updates"):
                for node_name, update in step.items():
                    events.put({"type": "node", "node": node_name})
                    if update.get("plan") is not None:
                        final_plan = update["plan"]

            if final_plan is None:
                message = "行程生成失败：服务未返回行程"
                trace.finalize(status="failure", error=message)
                events.put({"type": "error", "message": message})
            else:
                final_plan.user_preferences = list(merged.preferences or [])
                final_plan.departure_city = merged.departure_city
                final_plan.dietary_notes = merged.dietary_notes
                final_plan.hotel_budget = merged.hotel_budget
                final_plan.companions = merged.companions
                final_plan.user_memory = get_user_memory()
                trace.attach_plan(final_plan)
                events.put({"type": "done", "plan": final_plan})
        except Exception as exc:
            print(f"行程生成失败: {exc}")
            trace.finalize(status="failure", error=str(exc))
            events.put({"type": "error", "message": _friendly_error(exc)})
        finally:
            reset_progress_callback(token)
            events.put({"type": "exit"})


def _run_variants_stream(merged, events):
    def sink(message):
        events.put({"type": "progress", "message": message})

    token = set_progress_callback(sink)
    try:
        themes = pick_variant_themes(merged)
        for index, theme in enumerate(themes):
            events.put(
                {
                    "type": "variant-start",
                    "index": index,
                    "label": theme["label"],
                    "theme": theme["label"],
                    "pace": theme["pace"],
                    "total": len(themes),
                }
            )
            plan = build_variant_plan(merged, theme)
            events.put({"type": "variant-done", "plan": plan})
        events.put({"type": "done"})
    except Exception as exc:
        print(f"行程生成失败: {exc}")
        events.put({"type": "error", "message": _friendly_error(exc)})
    finally:
        reset_progress_callback(token)
        events.put({"type": "exit"})

@app.post("/api/trip/plan/stream")
def plan_trip_stream(req: TripRequest):
    def event_generator():
        try:
            merged = merge_memory_into_request(req)
        except Exception as exc:
            print(f"行程生成失败: {exc}")
            yield f"event: error\ndata: {json.dumps({'message': _friendly_error(exc)}, ensure_ascii=False)}\n\n"
            return

        events = queue.Queue()
        worker = threading.Thread(
            target=_run_plan_stream,
            args=(merged, events),
            daemon=True,
        )
        worker.start()
        yield from _sse_events(events)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/trip/plan/variants")
def plan_variants_endpoint(req: TripRequest):
    variants = plan_variants(merge_memory_into_request(req))
    return {"variants": [variant.model_dump() for variant in variants]}


@app.post("/api/trip/plan/variants/stream")
def plan_variants_stream(req: TripRequest):
    def event_generator():
        try:
            merged = merge_memory_into_request(req)
        except Exception as exc:
            print(f"行程生成失败: {exc}")
            yield f"event: error\ndata: {json.dumps({'message': _friendly_error(exc)}, ensure_ascii=False)}\n\n"
            return

        events = queue.Queue()
        worker = threading.Thread(
            target=_run_variants_stream,
            args=(merged, events),
            daemon=True,
        )
        worker.start()
        yield from _sse_events(events)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

class SaveHistoryRequest(BaseModel):
    plan: TripPlan


@app.post("/api/history")
def save_history(req: SaveHistoryRequest):
    update_memory_from_plan(req.plan)
    plan_id = save_plan(req.plan)
    return {"id": plan_id, "memory": get_user_memory()}


@app.get("/api/history")
def history_list():
    return list_plans()


@app.get("/api/history/{plan_id}")
def history_detail(plan_id: int):
    plan = get_plan(plan_id)
    if plan is None:
        return JSONResponse(status_code=404, content={"detail": "行程记录不存在"})
    return plan.model_dump()


@app.delete("/api/history/{plan_id}")
def history_delete(plan_id: int):
    if not delete_plan(plan_id):
        return JSONResponse(status_code=404, content={"detail": "not found"})
    return {"ok": True}


class MemoryUpdateRequest(BaseModel):
    preferences: list[str] = []
    visited_cities: list[str] = []
    dietary_notes: str = ""
    pace: str = ""
    transport_mode: str = ""
    hotel_budget: int = 0
    companions: int = 1


@app.get("/api/memory")
def memory_get():
    return get_user_memory()


@app.put("/api/memory")
def memory_update(req: MemoryUpdateRequest):
    return save_user_memory(req.model_dump())

class ChatRequest(BaseModel):
    messages: list[dict]
    session_id: int | None = None


@app.post("/api/chat")
def chat(req: ChatRequest):
    result = chat_requirement(req.messages, memory=get_user_memory())

    session_id = req.session_id
    if session_id is None or chat_service.get_session(session_id) is None:
        session_id = chat_service.create_session("新对话")

    user_content = ""
    for msg in reversed(req.messages):
        if msg.get("role") == "user" and str(msg.get("content") or "").strip():
            user_content = str(msg.get("content") or "").strip()
            break
    if user_content:
        chat_service.append_message(session_id, "user", user_content)

    reply = str(result.get("reply") or "").strip()
    if reply:
        chat_service.append_message(session_id, "assistant", reply)

    if result.get("ready"):
        data = result.get("trip_request") or {}
        destination = str(data.get("destination") or "").strip()
        days = int(data.get("days", 3) or 3)
        title = f"{destination} {days}日游" if destination else "旅行规划"
        chat_service.rename_session(session_id, title)
        result["trip_request"] = TripRequest(
            destination=destination,
            days=days,
            budget=int(data.get("budget", 3000)),
            preferences=data.get("preferences", []),
            departure_city=data.get("departure_city", ""),
            travel_date=data.get("travel_date", ""),
            pace=data.get("pace", "standard"),
            hotel_budget=int(data.get("hotel_budget", 0) or 0),
            dietary_notes=data.get("dietary_notes", ""),
            companions=int(data.get("companions", 1) or 1),
        )

    result["session_id"] = session_id
    result["title"] = chat_service.get_session(session_id)["title"]
    return result


@app.get("/api/chat/sessions")
def chat_sessions():
    return chat_service.list_sessions()


@app.get("/api/chat/sessions/{session_id}")
def chat_session_detail(session_id: int):
    session = chat_service.get_session(session_id)
    if session is None:
        return JSONResponse(status_code=404, content={"detail": "会话不存在"})
    session["messages"] = chat_service.get_messages(session_id)
    return session


@app.delete("/api/chat/sessions/{session_id}")
def chat_session_delete(session_id: int):
    if not chat_service.delete_session(session_id):
        return JSONResponse(status_code=404, content={"detail": "会话不存在"})
    return {"ok": True}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def not_found_route(path: str):
    return JSONResponse(status_code=404, content={"detail": "请求的接口不存在"})
