"""Read-only HTTP API exposing briefings and items as JSON.

Runs in a daemon thread alongside the scheduler and the Telegram chat
bot, so an external consumer (e.g. a scheduled Claude cloud routine) can
pull exactly the content that goes out via Telegram and post-process it.

Deliberately built on the standard library (`http.server`) — no extra
runtime dependency, no second async loop. Traffic is tiny (one client,
a handful of requests per day).

Endpoints (all GET, JSON):

    /health                          liveness, no auth
    /api/briefings/latest            newest briefing + its items
    /api/briefings/<YYYY-MM-DD>      one briefing + its items
    /api/briefings?limit=7           briefing summaries (no markdown)
    /api/items?since_days=1&category=action,relevant&limit=100
                                     items in window, optional filters

Auth: `Authorization: Bearer <JMNEWS_API_TOKEN>` (or `X-API-Key`).
If no token is configured the API does not start.
"""

from __future__ import annotations

import hmac
import json
import threading
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from loguru import logger

from jmnews import __version__
from jmnews.config import Settings
from jmnews.models import Briefing, NewsItem
from jmnews.storage import Storage

MAX_LIMIT = 500
MAX_SINCE_DAYS = 30


def item_to_dict(item: NewsItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "source": item.source,
        "title": item.title,
        "url": item.url,
        "published_at": item.published_at.isoformat(),
        "score": item.score,
        "category": item.category,
        "reasoning": item.reasoning,
        "snippet": item.snippet,
        "delivered_in_briefing_id": item.delivered_in_briefing_id,
    }


def briefing_to_dict(briefing: Briefing, items: list[NewsItem] | None = None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": briefing.id,
        "generated_at": briefing.generated_at.isoformat(),
        "delivered_at": briefing.delivered_at.isoformat() if briefing.delivered_at else None,
        "delivery_status": briefing.delivery_status,
        "item_count": briefing.item_count,
    }
    if items is not None:
        data["markdown"] = briefing.markdown
        data["items"] = [item_to_dict(i) for i in items]
    return data


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _int_param(query: dict[str, list[str]], key: str, default: int, maximum: int) -> int:
    raw = query.get(key, [None])[0]
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{key} must be an integer") from exc
    if value < 1:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{key} must be >= 1")
    return min(value, maximum)


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


class ApiRouter:
    """Maps a (path, query) to a JSON-serialisable response. Transport-agnostic."""

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def route(self, path: str, query: dict[str, list[str]]) -> Any:
        if path == "/api/briefings/latest":
            briefing = self._storage.latest_briefing()
            if briefing is None:
                raise ApiError(HTTPStatus.NOT_FOUND, "no briefing stored yet")
            return self._full_briefing(briefing)

        if path.startswith("/api/briefings/"):
            briefing_id = path.removeprefix("/api/briefings/")
            if not _is_iso_date(briefing_id):
                raise ApiError(HTTPStatus.BAD_REQUEST, "briefing id must be YYYY-MM-DD")
            briefing = self._storage.get_briefing(briefing_id)
            if briefing is None:
                raise ApiError(HTTPStatus.NOT_FOUND, f"no briefing for {briefing_id}")
            return self._full_briefing(briefing)

        if path == "/api/briefings":
            limit = _int_param(query, "limit", default=7, maximum=100)
            return {"briefings": [briefing_to_dict(b) for b in self._storage.list_briefings(limit)]}

        if path == "/api/items":
            since_days = _int_param(query, "since_days", default=1, maximum=MAX_SINCE_DAYS)
            limit = _int_param(query, "limit", default=100, maximum=MAX_LIMIT)
            raw_cat = query.get("category", [""])[0]
            categories = [c.strip() for c in raw_cat.split(",") if c.strip()] or None
            source = query.get("source", [None])[0]
            items = self._storage.list_items(
                since_days=since_days, categories=categories, source=source, limit=limit
            )
            return {"count": len(items), "items": [item_to_dict(i) for i in items]}

        raise ApiError(HTTPStatus.NOT_FOUND, "unknown endpoint")

    def _full_briefing(self, briefing: Briefing) -> dict[str, Any]:
        items = self._storage.get_items_in_briefing(briefing.id)
        return briefing_to_dict(briefing, items)


def _make_handler(router: ApiRouter, token: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"jmnews/{__version__}"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            logger.debug("api: " + format, *args)

        def _send_json(self, status: HTTPStatus, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            auth = self.headers.get("Authorization", "")
            presented = ""
            if auth.lower().startswith("bearer "):
                presented = auth[7:].strip()
            else:
                presented = self.headers.get("X-API-Key", "").strip()
            return bool(presented) and hmac.compare_digest(presented, token)

        def do_GET(self) -> None:  # noqa: N802
            parts = urlsplit(self.path)
            path = parts.path.rstrip("/") or "/"
            query = parse_qs(parts.query)

            if path == "/health":
                self._send_json(HTTPStatus.OK, {"status": "ok", "version": __version__})
                return
            if not self._authorized():
                logger.warning("api: unauthorized request from {}", self.client_address[0])
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            try:
                payload = router.route(path, query)
            except ApiError as exc:
                self._send_json(exc.status, {"error": exc.message})
                return
            except Exception as exc:  # noqa: BLE001
                logger.exception("api: handler crashed")
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"internal error: {exc}"}
                )
                return
            self._send_json(HTTPStatus.OK, payload)

    return Handler


def make_server(settings: Settings, storage: Storage) -> ThreadingHTTPServer:
    """Build (but do not start) the HTTP server. Raises if no token is set."""
    if not settings.api_token:
        raise ValueError("JMNEWS_API_TOKEN is empty")
    handler = _make_handler(ApiRouter(storage), settings.api_token)
    server = ThreadingHTTPServer((settings.api_host, settings.api_port), handler)
    server.daemon_threads = True
    return server


def run_in_thread(settings: Settings, storage: Storage) -> threading.Thread | None:
    """Start the API server in a daemon thread. Returns None if disabled."""
    if not settings.api_enabled:
        logger.info("api: disabled via JMNEWS_API_ENABLED=0")
        return None
    if not settings.api_token:
        logger.warning("api: JMNEWS_API_TOKEN missing — API disabled")
        return None
    try:
        server = make_server(settings, storage)
    except OSError as exc:
        logger.error("api: cannot bind {}:{} — {}", settings.api_host, settings.api_port, exc)
        return None
    th = threading.Thread(target=server.serve_forever, name="jmnews-api", daemon=True)
    th.start()
    logger.info("api: listening on {}:{}", settings.api_host, settings.api_port)
    return th


__all__ = ["ApiRouter", "make_server", "run_in_thread", "briefing_to_dict", "item_to_dict"]
