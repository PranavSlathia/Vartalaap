"""WhatsApp outbound messaging client using a webhook integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp


class WhatsAppSendError(RuntimeError):
    """Raised when WhatsApp message sending fails."""


@dataclass(slots=True)
class WhatsAppClient:
    """Send WhatsApp messages via a configured webhook."""

    webhook_url: str
    auth_token: str | None = None
    timeout_seconds: int = 10

    _session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> WhatsAppClient:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def send_message(
        self,
        phone: str,
        message: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self._session:
            raise WhatsAppSendError("Client session not initialized")

        payload = {
            "phone": phone,
            "message": message,
            "metadata": metadata or {},
        }
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        async with self._session.post(self.webhook_url, json=payload, headers=headers) as resp:
            if resp.status >= 400:
                body = await resp.text()
                raise WhatsAppSendError(f"Webhook failed: {resp.status} {body}")
