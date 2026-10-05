"""Ops endpoints: /healthz, /readyz, /metrics, /api/config (OBS-1, OBS-2, ADP-2)."""

import httpx

from app.main import create_app
from tests.conftest import make_settings, running_client


async def test_healthz_is_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_healthz_sets_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert len(response.headers["x-request-id"]) == 32


async def test_request_id_is_echoed_when_safe(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


async def test_unsafe_request_id_is_replaced(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz", headers={"X-Request-ID": "bad id\nwith newline"})
    assert response.headers["x-request-id"] != "bad id\nwith newline"


async def test_readyz_reports_not_configured(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "not_configured", "redis": "not_configured"},
    }


async def test_readyz_reports_unreachable_redis_as_degraded() -> None:
    # Port 1 on localhost refuses immediately: no network access needed.
    app = create_app(make_settings(redis_url="redis://127.0.0.1:1/0"))
    async with running_client(app) as http:
        response = await http.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "not_configured", "redis": "error"}


async def test_metrics_counts_requests(client: httpx.AsyncClient) -> None:
    await client.get("/healthz")
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "campus_pulse_uptime_seconds" in response.text
    assert 'campus_pulse_http_requests_total{status="200"}' in response.text


async def test_public_config_returns_institution_text(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/config")
    assert response.status_code == 200
    body = response.json()
    assert body["institution_slug"] == "lgu"
    assert body["disclaimer"].startswith("Answers are based on information verified")
    assert set(body) == {"institution_slug", "disclaimer"}  # never leaks other settings


async def test_cors_allows_configured_origin(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/healthz",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_cors_rejects_other_origin(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/healthz",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in response.headers
