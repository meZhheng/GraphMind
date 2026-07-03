import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from graphmind.agent.store import AgentSessionStore
from graphmind.core.config import DEFAULT_TASK, TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
session_store = AgentSessionStore()
logger = logging.getLogger("uvicorn.error")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_task": DEFAULT_TASK,
        },
    )


@router.websocket("/ws/agent")
async def agent_socket(websocket: WebSocket):
    await websocket.accept()
    requested_session_id = websocket.query_params.get("session_id")
    session, restored = session_store.get_or_create(requested_session_id)
    await websocket.send_json(
        {
            "category": "session",
            "title": "Session started",
            "session_id": session.id,
            "requested_session_id": requested_session_id,
            "restored": restored,
            "context": session.context_payload,
            "pending_confirmation": session.pending_confirmation_payload,
            "session_status": session.status_payload,
        },
    )

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")
            logger.info(
                "session=%s websocket message=%s status=%s",
                session.id,
                message_type,
                session.status_payload,
            )

            if message_type == "run":
                content = str(message.get("content", "")).strip()
                if not content:
                    await websocket.send_json(
                        {
                            "category": "error",
                            "title": "Empty task",
                            "content": "Please enter a task.",
                        },
                    )
                    continue

                async for payload in session.stream_task(content):
                    await websocket.send_json(payload)

            elif message_type == "confirm":
                async for payload in session.stream_confirmation(
                    message.get("results", []),
                ):
                    await websocket.send_json(payload)

            else:
                await websocket.send_json(
                    {
                        "category": "error",
                        "title": "Unknown message",
                        "content": f"Unsupported message type: {message_type}",
                    },
                )

    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.exception("agent websocket failed for session=%s", session.id)
        try:
            await websocket.send_json(
                {
                    "category": "error",
                    "title": "WebSocket failed",
                    "content": f"{exc.__class__.__name__}: {exc}",
                    "context": session.context_payload,
                    "session_status": session.status_payload,
                },
            )
        except Exception:
            pass
        return
