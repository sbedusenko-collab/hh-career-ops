"""
OAuth2 авторизация для hh.ru API.

Флоу:
  1. python -m src.api.auth  — открывает браузер, запускает локальный сервер
  2. Пользователь логинится на hh.ru
  3. Токены сохраняются в config.yaml автоматически
"""

import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import yaml

CONFIG_PATH = "config.yaml"
TOKEN_URL = "https://hh.ru/oauth/token"
AUTH_URL = "https://hh.ru/oauth/authorize"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def save_tokens(access_token: str, refresh_token: str) -> None:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)
    config["hh"]["access_token"] = access_token
    config["hh"]["refresh_token"] = refresh_token
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
    print("Токены сохранены в config.yaml")


def refresh_access_token() -> str:
    """Обновляет access_token используя refresh_token. Возвращает новый access_token."""
    config = load_config()
    hh = config["hh"]

    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": hh["refresh_token"],
            "client_id": hh["client_id"],
            "client_secret": hh["client_secret"],
        },
    )
    resp.raise_for_status()
    data = resp.json()
    save_tokens(data["access_token"], data["refresh_token"])
    return data["access_token"]


def get_access_token() -> str:
    """Возвращает актуальный access_token, при необходимости обновляет."""
    config = load_config()
    token = config["hh"].get("access_token", "")
    if not token:
        raise RuntimeError("Токен не найден. Запусти: python -m src.api.auth")
    return token


# --- Однократная авторизация через браузер ---

_auth_code: str | None = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>OK! Вернись в терминал.</h2>".encode("utf-8"))
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>Ошибка: code не получен.</h2>".encode("utf-8"))

    def log_message(self, *args):
        pass  # тихий режим


def authorize() -> None:
    """Полный OAuth2 флоу: открывает браузер → получает code → меняет на токены."""
    config = load_config()
    hh = config["hh"]

    params = urlencode({
        "response_type": "code",
        "client_id": hh["client_id"],
        "redirect_uri": hh["redirect_uri"],
    })
    auth_url = f"{AUTH_URL}?{params}"

    port = int(hh.get("callback_local_port", urlparse(hh["redirect_uri"]).port or 8080))
    server = HTTPServer(("localhost", port), _CallbackHandler)

    print(f"Открываю браузер для авторизации...\n{auth_url}")
    webbrowser.open(auth_url)

    # Ждём callback (один вызов, блокирующий)
    server.handle_request()

    if not _auth_code:
        raise RuntimeError("Не удалось получить код авторизации.")

    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": _auth_code,
            "client_id": hh["client_id"],
            "client_secret": hh["client_secret"],
            "redirect_uri": hh["redirect_uri"],
        },
    )
    resp.raise_for_status()
    data = resp.json()
    save_tokens(data["access_token"], data["refresh_token"])
    print("Авторизация успешна!")


if __name__ == "__main__":
    authorize()
