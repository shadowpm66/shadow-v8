from __future__ import annotations

import os
from typing import Any

import requests


class TelegramBot:
    def __init__(self) -> None:
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    def send(self, message: str) -> bool:
        if not self.token or not self.chat_id:
            print(message)
            return False
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            for chunk in self._chunks(message):
                response = requests.post(url, data={"chat_id": self.chat_id, "text": chunk}, timeout=10)
                response.raise_for_status()
            return True
        except Exception as exc:
            print(f"Telegram send failed: {exc}")
            return False

    def get_updates(self, offset: int | None = None, timeout: int = 1) -> list[dict[str, Any]]:
        if not self.token:
            return []
        try:
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            params: dict[str, Any] = {"timeout": timeout}
            if offset is not None:
                params["offset"] = offset
            response = requests.get(url, params=params, timeout=timeout + 5)
            response.raise_for_status()
            payload = response.json()
            if not payload.get("ok"):
                return []
            return payload.get("result") or []
        except Exception as exc:
            print(f"Telegram getUpdates failed: {exc}")
            return []

    def is_authorized_chat(self, chat_id: Any) -> bool:
        if not self.chat_id:
            return False
        return str(chat_id) == str(self.chat_id)

    def _chunks(self, message: str, size: int = 3900) -> list[str]:
        if len(message) <= size:
            return [message]
        return [message[i : i + size] for i in range(0, len(message), size)]
