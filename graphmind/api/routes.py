import uuid

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from graphmind.agent.session import AgentSession
from graphmind.core.config import DEFAULT_TASK, TEMPLATES_DIR


router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


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
    session = AgentSession(id=str(uuid.uuid4()))
    await websocket.send_json(
        {
            "category": "session",
            "title": "Session started",
            "session_id": session.id,
            "context": {
                "current_tokens": session.current_context_tokens,
                "max_tokens": session.agent.model.context_size,
            },
        },
    )

    try:
        while True:
            message = await websocket.receive_json()
            message_type = message.get("type")

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
