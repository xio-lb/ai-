import json
import queue
import threading
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.agents.chat_agent import chat_requirement
from app.agents.graph import trip_graph
from app.agents.orchestrator import (
    adjust_trip,
    build_variant_plan,
    pick_variant_themes,
    plan_trip,
    plan_variants,
)
from app.schemas.trip import TripPlan, TripRequest
from app.services import auth_service, chat_service, observability, tasks_service
from app.services.amap_client import build_route_legs
from app.services.history_service import delete_plan, get_plan, init_db, list_plans, save_plan
from app.services.memory_service import (
    get_user_memory,
    merge_memory_into_request,
    save_user_memory,
    update_memory_from_plan,
)
from app.services.observability import trace_generation
from app.services.progress import reset_progress_callback, set_progress_callback

REQUIRE_AUTH = False


def _require_auth() -> bool:
    import os

    return os.getenv("REQUIRE_AUTH", "false").strip().lower() in {"1", "true", "yes", "on"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    auth_service.init_db()
    init_db()
    chat_service.init_db()
    observability.init_db()
    tasks_service.init_db()
    tasks_service.start_workers()
    yield
    tasks_service.stop_workers()


app = FastAPI(title="AI Travel Planner", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "请求参数有误，请检查后重试"})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) and exc.detail else "请求处理失败，请稍后重试"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": _friendly_error(exc)})


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=60)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _resolve_user(authorization: str | None) -> tuple[int, dict]:
    token = _extract_bearer(authorization)
    if token:
        try:
            payload = auth_service.decode_access_token(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        user = auth_service.get_user_by_id(int(payload["sub"]))
        if user is None or user["status"] != "active":
            raise HTTPException(status_code=401, detail="账号不可用，请重新登录")
        return int(user["id"]), user

    if _require_auth():
        raise HTTPException(status_code=401, detail="请先登录后再操作")
    user = auth_service.get_user_by_id(auth_service.ANONYMOUS_USER_ID) or {
        "id": auth_service.ANONYMOUS_USER_ID,
        "email": auth_service.ANONYMOUS_EMAIL,
        "display_name": "公共演示账号",
        "role": "system",
        "status": "active",
        "created_at": "",
    }
    return auth_service.ANONYMOUS_USER_ID, user


def current_user(authorization: Annotated[str | None, Header()] = None) -> tuple[int, dict]:
    return _resolve_user(authorization)


CurrentUser = Annotated[tuple[int, dict], Depends(current_user)]


@app.post("/api/auth/register")
def auth_register(req: RegisterRequest):
    try:
        user = auth_service.register_user(req.email, req.password, req.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token, meta = auth_service.create_access_token(int(user["id"]))
    return {"token": token, "token_type": "bearer", **meta, "user": user}


@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    import os

    window = int(os.getenv("AUTH_LOGIN_WINDOW_SECONDS", "900"))
    max_attempts = int(os.getenv("AUTH_LOGIN_MAX_ATTEMPTS", "10"))
    subject = req.email.strip().lower()
    if auth_service.login_failure_count(subject, window) >= max_attempts:
        raise HTTPException(status_code=429, detail="登录尝试过于频繁，请稍后再试")

    user = auth_service.authenticate_user(req.email, req.password)
    if user is None:
        auth_service.record_login_attempt(subject, succeeded=False)
        raise HTTPException(status_code=401, detail="邮箱或密码不正确")
    auth_service.clear_login_failures(subject)
    auth_service.record_login_attempt(subject, succeeded=True)
    token, meta = auth_service.create_access_token(int(user["id"]))
    return {"token": token, "token_type": "bearer", **meta, "user": user}


@app.get("/api/auth/me")
def auth_me(user: CurrentUser):
    _, profile = user
    return {"user": profile}


@app.post("/api/auth/logout")
def auth_logout(authorization: Annotated[str | None, Header()] = None):
    token = _extract_bearer(authorization)
    if token:
        auth_service.revoke_token(token)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Trip planning
# ---------------------------------------------------------------------------


class AdjustRequest(BaseModel):
    current_plan: TripPlan
    user_message: str


class RouteRecalcRequest(BaseModel):
    plan: TripPlan
    transport_mode: str = "auto"


@app.post("/api/trip/plan/adjust")
def adjust_trip_endpoint(req: AdjustRequest, user: CurrentUser):
    user_id, _ = user
    plan = adjust_trip(req.current_plan, req.user_message, user_id=user_id)
    return plan.model_dump()


@app.post("/api/trip/plan/routes")
def recalc_routes_endpoint(req: RouteRecalcRequest, user: CurrentUser):
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
def plan_trip_endpoint(req: TripRequest, user: CurrentUser):
    user_id, _ = user
    plan = plan_trip(merge_memory_into_request(req, user_id), user_id=user_id)
    return plan.model_dump()


def _friendly_error(exc: Exception) -> str:
    message = str(exc).strip()
    lower = message.lower()
    if "openai" in lower or "deepseek" in lower or "api error" in lower:
        return "AI 服务暂时不可用，请稍后重试"
    if message and ("高德" in message or "行程" in message or "服务" in message or "任务" in message):
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


def _run_plan_stream(merged, events, user_id: int = auth_service.LEGACY_USER_ID):
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
                final_plan.user_memory = get_user_memory(user_id)
                trace.attach_plan(final_plan)
                events.put({"type": "done", "plan": final_plan})
        except Exception as exc:
            print(f"行程生成失败: {exc}")
            trace.finalize(status="failure", error=str(exc))
            events.put({"type": "error", "message": _friendly_error(exc)})
        finally:
            reset_progress_callback(token)
            events.put({"type": "exit"})


def _run_variants_stream(merged, events, user_id: int = auth_service.LEGACY_USER_ID):
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
            plan = build_variant_plan(merged, theme, user_id=user_id)
            events.put({"type": "variant-done", "plan": plan})
        events.put({"type": "done"})
    except Exception as exc:
        print(f"行程生成失败: {exc}")
        events.put({"type": "error", "message": _friendly_error(exc)})
    finally:
        reset_progress_callback(token)
        events.put({"type": "exit"})


@app.post("/api/trip/plan/stream")
def plan_trip_stream(req: TripRequest, user: CurrentUser):
    user_id, _ = user

    def event_generator():
        try:
            merged = merge_memory_into_request(req, user_id)
        except Exception as exc:
            print(f"行程生成失败: {exc}")
            yield f"event: error\ndata: {json.dumps({'message': _friendly_error(exc)}, ensure_ascii=False)}\n\n"
            return

        events = queue.Queue()
        worker = threading.Thread(
            target=_run_plan_stream,
            args=(merged, events, user_id),
            daemon=True,
        )
        worker.start()
        yield from _sse_events(events)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/trip/plan/variants")
def plan_variants_endpoint(req: TripRequest, user: CurrentUser):
    user_id, _ = user
    variants = plan_variants(merge_memory_into_request(req, user_id), user_id=user_id)
    return {"variants": [variant.model_dump() for variant in variants]}


@app.post("/api/trip/plan/variants/stream")
def plan_variants_stream(req: TripRequest, user: CurrentUser):
    user_id, _ = user

    def event_generator():
        try:
            merged = merge_memory_into_request(req, user_id)
        except Exception as exc:
            print(f"行程生成失败: {exc}")
            yield f"event: error\ndata: {json.dumps({'message': _friendly_error(exc)}, ensure_ascii=False)}\n\n"
            return

        events = queue.Queue()
        worker = threading.Thread(
            target=_run_variants_stream,
            args=(merged, events, user_id),
            daemon=True,
        )
        worker.start()
        yield from _sse_events(events)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Async tasks
# ---------------------------------------------------------------------------


class TaskSubmitRequest(BaseModel):
    request: TripRequest


@app.post("/api/tasks/plan", status_code=202)
def submit_plan_task(req: TaskSubmitRequest, user: CurrentUser):
    user_id, _ = user
    if tasks_service.submit_rate_limited(user_id):
        raise HTTPException(status_code=429, detail="提交过于频繁，请稍后再试")
    if tasks_service.count_running(user_id) >= tasks_service.MAX_RUNNING_PER_USER:
        raise HTTPException(status_code=429, detail="进行中的规划任务过多，请等待完成后再提交")
    task = tasks_service.create_task(user_id, req.request)
    return {"task_id": task["task_id"], "status": task["status"]}


@app.get("/api/tasks/{task_id}")
def get_plan_task(task_id: str, user: CurrentUser):
    user_id, _ = user
    task = tasks_service.get_task(task_id, user_id)
    if task is None:
        return JSONResponse(status_code=404, content={"detail": "任务不存在"})
    return task


@app.get("/api/tasks")
def list_plan_tasks(user: CurrentUser, limit: int = 20):
    user_id, _ = user
    return {"items": tasks_service.list_tasks(user_id, limit=limit)}


@app.post("/api/tasks/{task_id}/cancel")
def cancel_plan_task(task_id: str, user: CurrentUser):
    user_id, _ = user
    if not tasks_service.cancel_task(task_id, user_id):
        return JSONResponse(status_code=404, content={"detail": "任务不存在"})
    return {"ok": True}


@app.get("/api/tasks/{task_id}/stream")
def stream_plan_task(task_id: str, user: CurrentUser):
    import time

    user_id, _ = user

    def event_generator():
        last_message = ""
        while True:
            task = tasks_service.get_task(task_id, user_id)
            if task is None:
                yield 'event: error\ndata: {"message": "任务不存在"}\n\n'
                return
            message = task.get("progress_message") or ""
            if message and message != last_message:
                last_message = message
                yield f"event: progress\ndata: {json.dumps({'message': message}, ensure_ascii=False)}\n\n"
            if task["status"] in tasks_service.TERMINAL_STATUSES:
                if task["status"] == "succeeded" and task.get("plan") is not None:
                    yield f"event: done\ndata: {json.dumps(task['plan'], ensure_ascii=False)}\n\n"
                elif task["status"] == "failed":
                    yield f"event: error\ndata: {json.dumps({'message': task['error']}, ensure_ascii=False)}\n\n"
                else:
                    yield "event: cancelled\ndata: {}\n\n"
                return
            time.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class SaveHistoryRequest(BaseModel):
    plan: TripPlan


@app.post("/api/history")
def save_history(req: SaveHistoryRequest, user: CurrentUser):
    user_id, _ = user
    update_memory_from_plan(req.plan, user_id)
    plan_id = save_plan(req.plan, user_id)
    return {"id": plan_id, "memory": get_user_memory(user_id)}


@app.get("/api/history")
def history_list(user: CurrentUser):
    user_id, _ = user
    return list_plans(user_id)


@app.get("/api/history/{plan_id}")
def history_detail(plan_id: int, user: CurrentUser):
    user_id, _ = user
    plan = get_plan(plan_id, user_id)
    if plan is None:
        return JSONResponse(status_code=404, content={"detail": "行程记录不存在"})
    return plan.model_dump()


@app.delete("/api/history/{plan_id}")
def history_delete(plan_id: int, user: CurrentUser):
    user_id, _ = user
    if not delete_plan(plan_id, user_id):
        return JSONResponse(status_code=404, content={"detail": "not found"})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class MemoryUpdateRequest(BaseModel):
    preferences: list[str] = []
    visited_cities: list[str] = []
    dietary_notes: str = ""
    pace: str = ""
    transport_mode: str = ""
    hotel_budget: int = 0
    companions: int = 1


@app.get("/api/memory")
def memory_get(user: CurrentUser):
    user_id, _ = user
    return get_user_memory(user_id)


@app.put("/api/memory")
def memory_update(req: MemoryUpdateRequest, user: CurrentUser):
    user_id, _ = user
    return save_user_memory(req.model_dump(), user_id)


# ---------------------------------------------------------------------------
# Chat sessions
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    messages: list[dict]
    session_id: int | None = None


@app.post("/api/chat")
def chat(req: ChatRequest, user: CurrentUser):
    user_id, _ = user
    result = chat_requirement(req.messages, memory=get_user_memory(user_id))

    session_id = req.session_id
    if session_id is None or chat_service.get_session(session_id, user_id) is None:
        session_id = chat_service.create_session("新对话", user_id)

    user_content = ""
    for msg in reversed(req.messages):
        if msg.get("role") == "user" and str(msg.get("content") or "").strip():
            user_content = str(msg.get("content") or "").strip()
            break
    if user_content:
        chat_service.append_message(session_id, "user", user_content, user_id)

    reply = str(result.get("reply") or "").strip()
    if reply:
        chat_service.append_message(session_id, "assistant", reply, user_id)

    if result.get("ready"):
        data = result.get("trip_request") or {}
        destination = str(data.get("destination") or "").strip()
        days = int(data.get("days", 3) or 3)
        title = f"{destination} {days}日游" if destination else "旅行规划"
        chat_service.rename_session(session_id, title, user_id)
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
    result["title"] = chat_service.get_session(session_id, user_id)["title"]
    return result


@app.get("/api/chat/sessions")
def chat_sessions(user: CurrentUser):
    user_id, _ = user
    return chat_service.list_sessions(user_id)


@app.get("/api/chat/sessions/{session_id}")
def chat_session_detail(session_id: int, user: CurrentUser):
    user_id, _ = user
    session = chat_service.get_session(session_id, user_id)
    if session is None:
        return JSONResponse(status_code=404, content={"detail": "会话不存在"})
    session["messages"] = chat_service.get_messages(session_id, user_id)
    return session


@app.delete("/api/chat/sessions/{session_id}")
def chat_session_delete(session_id: int, user: CurrentUser):
    user_id, _ = user
    if not chat_service.delete_session(session_id, user_id):
        return JSONResponse(status_code=404, content={"detail": "会话不存在"})
    return {"ok": True}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
async def not_found_route(path: str):
    return JSONResponse(status_code=404, content={"detail": "请求的接口不存在"})
