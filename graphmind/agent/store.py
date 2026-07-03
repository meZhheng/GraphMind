from __future__ import annotations

import uuid

from graphmind.agent.session import AgentSession


class AgentSessionStore:
    """In-memory agent sessions for WebSocket reconnects."""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentSession] = {}

    def create(self) -> AgentSession:
        session = AgentSession(id=str(uuid.uuid4()))
        self._sessions[session.id] = session
        return session

    def create_with_id(self, session_id: str) -> AgentSession:
        session = AgentSession(id=session_id)
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str | None) -> AgentSession | None:
        if not session_id:
            return None
        return self._sessions.get(session_id)

    def get_or_create(
        self,
        session_id: str | None = None,
    ) -> tuple[AgentSession, bool]:
        session = self.get(session_id)
        if session is not None:
            return session, True
        if session_id:
            try:
                uuid.UUID(session_id)
            except ValueError:
                pass
            else:
                return self.create_with_id(session_id), True
        return self.create(), False
