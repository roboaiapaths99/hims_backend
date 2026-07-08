from fastapi import FastAPI
import socketio
from typing import Dict, Any

class RealtimeNotificationService:
    _sio: socketio.AsyncServer = None

    @classmethod
    def set_sio(cls, sio: socketio.AsyncServer):
        """Set the global Socket.IO server instance."""
        cls._sio = sio

    @classmethod
    async def emit_to_branch(cls, branch_id: str, event_name: str, payload: Dict[str, Any]):
        """Emit a WebSocket event to all clients registered in a branch room."""
        if cls._sio:
            room = f"branch_{branch_id}"
            await cls._sio.emit(event_name, payload, room=room)
            print(f"[WS OUTBOUND] Sent event '{event_name}' to room '{room}' with payload keys: {list(payload.keys())}")
        else:
            print(f"[WS OFF] Event '{event_name}' skipped (Socket.IO not initialized)")

    @classmethod
    async def emit_to_user(cls, user_id: str, event_name: str, payload: Dict[str, Any]):
        """Emit a WebSocket event to a specific user (room: user_id)."""
        if cls._sio:
            room = f"user_{user_id}"
            await cls._sio.emit(event_name, payload, room=room)
            print(f"[WS OUTBOUND] Sent event '{event_name}' to room '{room}'")
        else:
            print(f"[WS OFF] Event '{event_name}' skipped (Socket.IO not initialized)")
