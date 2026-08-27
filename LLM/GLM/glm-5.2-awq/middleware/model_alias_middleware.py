import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class AnyModelAliasMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.target_model = os.environ["VLLM_DEFAULT_MODEL"]

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].startswith("/v1/")
        ):
            await self.app(scope, receive, send)
            return

        messages: list[Message] = []
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request" or not message.get(
                "more_body", False
            ):
                break

        body = b"".join(
            message.get("body", b"")
            for message in messages
            if message["type"] == "http.request"
        )

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            await self._forward(scope, messages, receive, send)
            return

        if not isinstance(payload, dict) or "model" not in payload:
            await self._forward(scope, messages, receive, send)
            return

        payload["model"] = self.target_model
        rewritten_body = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        rewritten_message: Message = {
            "type": "http.request",
            "body": rewritten_body,
            "more_body": False,
        }

        rewritten_scope = dict(scope)
        rewritten_scope["headers"] = [
            (name, value)
            for name, value in scope.get("headers", [])
            if name.lower() != b"content-length"
        ] + [(b"content-length", str(len(rewritten_body)).encode("ascii"))]

        await self._forward(rewritten_scope, [rewritten_message], receive, send)

    async def _forward(
        self,
        scope: dict[str, Any],
        messages: list[Message],
        receive: Receive,
        send: Send,
    ) -> None:
        queued = iter(messages)

        async def replay_receive() -> Message:
            try:
                return next(queued)
            except StopIteration:
                return await receive()

        await self.app(scope, replay_receive, send)
