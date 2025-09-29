"""
title: N8N AI Agent Connector
author: Colin Wheeler / House of Data, Switzerland
author_url: https://github.com/House-of-Data
funding_url: https://github.com/House-of-Data/openwebui-n8n-pipe
version: 1.0.0
"""

"""
Pipe: N8N AI Agent Connector

Purpose:
--------
This pipe connects Open WebUI to an external n8n workflow. It sends the user’s
current message and metadata to n8n, which routes the request to an AI Agent
node (backed by any model provider such as OpenAI, Ollama, or local LLMs) and
returns the generated result.

How it works:
-------------
1. Extracts the most recent user message from Open WebUI.
2. Packages the message and session metadata (chat_id, message_id, session_id,
   user info) into a JSON payload.
3. Sends the payload via HTTP POST to a configured n8n webhook (production or
   test), with optional authentication and trace headers.
4. Expects a JSON array response from n8n:
   - The first item contains the `output` field with the agent’s reply.
   - The `intermediateSteps` field may exist but is not required.
5. Returns the value of `output` to Open WebUI as a single, non-streaming
   message.

Key characteristics:
--------------------
- Non-streaming: Open WebUI treats all responses as final.
- Timeout-aware: configurable timeout to handle long-running generations.
- Metadata-rich: forwards chat, session, message, and user identifiers as HTTP
  headers and payload, supporting both logging and memory management.
- Configurable: server address, webhook path, authentication headers, and
  timeout are adjustable through valves.

Metadata handling:
------------------
- Chat ID, Message ID, and Session ID are always included.
- User ID is always included.
- User details (name, timezone, language, location) are optional.
- User profile picture is optional.

Intended usage:
---------------
Use this pipe when Open WebUI acts as a front-end and n8n provides the
orchestration layer, including AI Agent calls, memory handling, post-processing,
and optional intermediate reasoning steps.

Repository:
-----------
https://github.com/House-of-Data/openwebui-n8n-pipe

Authors:
--------
- Colin Wheeler, House of Data, Switzerland
- ChatGPT (collaborative development and review)
"""

from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
import requests
import json


def _dumps(obj: Any) -> str:
    """Simple JSON dump helper (kept minimal on purpose)."""
    return json.dumps(obj, ensure_ascii=False)


class Pipe:
    class Valves(BaseModel):
        # --- Connection / endpoint ---
        SERVER_ADDRESS: str = Field(
            default="http://n8n:5678", description="Base URL to n8n (no trailing slash)"
        )
        WEBHOOK_ENV: Literal["production", "test"] = Field(
            default="production", description="Select 'webhook' or 'webhook-test' path"
        )
        WEBHOOK_PATH: str = Field(
            default="", description="Webhook ID/path only (no leading slash)"
        )

        # --- Auth / headers ---
        AUTH_HEADER_KEY: str = Field(default="Authorization")
        AUTH_HEADER_VALUE: str = Field(default="")
        EXTRA_HEADERS_JSON: str = Field(
            default="{}", description="Additional static headers as a JSON object"
        )

        # --- Behaviour ---
        TIMEOUT_SECONDS: int = Field(
            default=120, ge=1, le=600, description="Read timeout for n8n response"
        )
        DEBUG_LOG_IDS: bool = Field(
            default=False, description="Print chat/message/session IDs to server logs"
        )

        # --- Metadata options (IDs always included; user fields optional) ---
        INCLUDE_USER_NAME: bool = True
        INCLUDE_USER_TIMEZONE: bool = True
        INCLUDE_USER_LANGUAGE: bool = True
        INCLUDE_USER_LOCATION: bool = True
        INCLUDE_USER_PICTURE: bool = False  # off by default

        # --- Debugging ---
        INCLUDE_DEBUG_REQUEST_BODY: bool = Field(
            default=False,
            description=(
                "If true, include the full OpenWebUI request body in the payload "
                "(for troubleshooting only)."
            ),
        )

    def __init__(self):
        self.valves = self.Valves()
        self.type = "pipe"

    # --- Helpers -------------------------------------------------------------

    def _compose_webhook_url(self) -> str:
        """Build the n8n webhook URL from valves."""
        base = (self.valves.SERVER_ADDRESS or "").strip().rstrip("/")
        path = (self.valves.WEBHOOK_PATH or "").strip().strip("/")
        if not base or not path:
            return ""
        suffix = "webhook-test" if self.valves.WEBHOOK_ENV == "test" else "webhook"
        return f"{base}/{suffix}/{path}"

    def _get_latest_user_message(self, body: Dict[str, Any]) -> str:
        """Extract the most recent 'user' message; fall back to last message content."""
        messages: List[Dict[str, Any]] = body.get("messages") or []
        # Prefer the last role=='user'
        for m in reversed(messages):
            if (m.get("role") or "").lower() == "user":
                return m.get("content", "") or ""
        # Fallback: last message content (if any)
        return messages[-1].get("content", "") if messages else ""

    def _collect_metadata(
        self,
        body: Dict[str, Any],
        __metadata__: Optional[Dict[str, Any]],
        __user__: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Collect chat/session/message/user identifiers.
        - chat_id, message_id, session_id: always included (stringified)
        - user: user.id always included; other fields included per valves.
        """
        # Merge any metadata sources (OpenWebUI sometimes nests under openwebui_body.metadata)
        md: Dict[str, Any] = {}
        for source in (
            body.get("metadata"),
            (body.get("openwebui_body") or {}).get("metadata"),
            __metadata__,
        ):
            if isinstance(source, Dict):
                md.update(source)

        # IDs: try multiple common keys
        chat_id = (
            md.get("chat_id")
            or md.get("chatId")
            or body.get("chat_id")
            or (body.get("chat") or {}).get("id")
            or ""
        )
        message_id = (
            md.get("message_id")
            or md.get("messageId")
            or (
                (body.get("messages") or [])[-1].get("id")
                if body.get("messages")
                else None
            )
            or ""
        )
        session_id = (
            md.get("session_id")
            or md.get("sessionId")
            or body.get("session_id")
            or (body.get("session") or {}).get("id")
            or ""
        )

        # User info: prefer explicit __user__, fall back to body/openwebui_body.user
        user_info = (
            __user__
            or (body.get("openwebui_body") or {}).get("user")
            or body.get("user")
            or {}
        )
        if not isinstance(user_info, Dict):
            user_info = {}

        # Always include user_id (may be empty string if not present)
        user_id = (
            user_info.get("id")
            or md.get("user_id")
            or (body.get("user") or {}).get("id")
            or ""
        )

        # Optionally include other user fields
        user_payload: Dict[str, Any] = {"id": str(user_id)}
        if self.valves.INCLUDE_USER_NAME and "name" in user_info:
            user_payload["name"] = user_info.get("name")
        if self.valves.INCLUDE_USER_TIMEZONE and "timezone" in user_info:
            user_payload["timezone"] = user_info.get("timezone")
        if self.valves.INCLUDE_USER_LANGUAGE and "language" in user_info:
            user_payload["language"] = user_info.get("language")
        if self.valves.INCLUDE_USER_LOCATION and "location" in user_info:
            user_payload["location"] = user_info.get("location")
        if self.valves.INCLUDE_USER_PICTURE and "picture" in user_info:
            user_payload["picture"] = user_info.get("picture")

        return {
            "chat_id": str(chat_id),
            "message_id": str(message_id),
            "session_id": str(session_id),
            "user": user_payload,
            "metadata": md,  # pass through raw metadata for n8n memory logic
        }

    # --- Main entry ----------------------------------------------------------

    def pipe(
        self,
        body: Dict[str, Any],
        __metadata__: Optional[Dict[str, Any]] = None,
        __user__: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        url = self._compose_webhook_url()
        if not url:
            return "N8N: SERVER_ADDRESS / WEBHOOK_PATH not configured."

        # Extract message + metadata (no chat history here)
        message = self._get_latest_user_message(body)
        meta = self._collect_metadata(body, __metadata__, __user__)

        # Headers
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.valves.AUTH_HEADER_VALUE:
            headers[self.valves.AUTH_HEADER_KEY] = self.valves.AUTH_HEADER_VALUE

        # Extra static headers (JSON object)
        try:
            extra = json.loads(self.valves.EXTRA_HEADERS_JSON or "{}")
            if isinstance(extra, dict):
                for k, v in extra.items():
                    if isinstance(k, str) and isinstance(v, str):
                        headers[k] = v
        except Exception:
            pass

        # Trace headers (useful for logging + memory management on n8n side)
        headers["X-Chat-Id"] = meta["chat_id"]
        headers["X-Message-Id"] = meta["message_id"]
        headers["X-Session-Id"] = meta["session_id"]
        if self.valves.DEBUG_LOG_IDS:
            print(
                f"[N8N] chat={meta['chat_id']} message={meta['message_id']} session={meta['session_id']}"
            )

        # --- Payload build ---
        payload: Dict[str, Any] = {
            "agent": {
                "name": "N8N AI Agent Connector",
                "version": "1.0.0",
                "env": self.valves.WEBHOOK_ENV,
            },
            "message": message,
            "chat_id": meta["chat_id"],
            "message_id": meta["message_id"],
            "session_id": meta["session_id"],
            "user": meta["user"],
            "metadata": meta["metadata"] or None,
        }

        if self.valves.INCLUDE_DEBUG_REQUEST_BODY:
            payload["openwebui_body"] = body

        # --- HTTP POST + response handling ---
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=(10, self.valves.TIMEOUT_SECONDS),
            )
        except requests.RequestException as e:
            return f"n8n error: {e}"

        if not (200 <= resp.status_code < 300):
            text = (resp.text or "").strip()
            if len(text) > 600:
                text = text[:600] + "…"
            return f"n8n HTTP {resp.status_code}: {text}"

        try:
            data = resp.json()
        except ValueError:
            return resp.text or "n8n returned an empty body."

        # Default n8n behaviour: respond with first item (a dict)
        if isinstance(data, dict):
            out = data.get("output")
            if out is not None:
                return str(out)

        return "n8n response missing 'output'."