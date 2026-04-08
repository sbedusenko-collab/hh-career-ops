"""
Базовый HTTP-клиент для hh.ru API с автоматическим retry и refresh токена.
"""

import time
from typing import Any

import httpx

from src.api.auth import get_access_token, refresh_access_token

BASE_URL = "https://api.hh.ru"
USER_AGENT = "hh-career-ops/1.0 (job search automation)"


class HHClient:
    def __init__(self):
        self._token = get_access_token()
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={
                "User-Agent": USER_AGENT,
                "HH-User-Agent": USER_AGENT,
            },
            timeout=30,
        )

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    def get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, data: dict | None = None, json: dict | None = None) -> Any:
        return self._request("POST", path, data=data, json=json)

    def _request(self, method: str, path: str, *, retries: int = 3, **kwargs) -> Any:
        for attempt in range(retries):
            resp = self._client.request(
                method, path, headers=self._headers(), **kwargs
            )

            if resp.status_code == 401:
                # Токен протух — обновляем и повторяем
                self._token = refresh_access_token()
                continue

            if resp.status_code == 429:
                # Rate limit — ждём экспоненциально
                wait = 2 ** attempt
                print(f"Rate limit, жду {wait}s...")
                time.sleep(wait)
                continue

            if resp.status_code == 403:
                raise PermissionError(f"403 Forbidden: {resp.text}")

            resp.raise_for_status()
            return resp.json() if resp.content else None

        raise RuntimeError(f"Запрос не выполнен после {retries} попыток: {method} {path}")
