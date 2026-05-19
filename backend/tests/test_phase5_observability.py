"""Phase 5 — observability surface: /healthz, /readyz, /metrics, JSON logging."""

from __future__ import annotations

import json

from app.core.observability import (
    JsonFormatter,
    agent_decisions_total,
    http_requests_total,
    render_metrics,
    webhook_inbound_total,
)


def test_healthz_returns_ok(client):
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_readyz_returns_ok_when_db_reachable(client):
    res = client.get("/readyz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"


def test_metrics_endpoint_serves_prometheus_format(client):
    # Exercise an endpoint so the http_requests counter has at least one sample.
    client.get("/health")
    res = client.get("/metrics")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    body = res.text
    # Each declared metric family must appear in the exposition output.
    for family in (
        "http_requests_total",
        "http_request_duration_seconds",
        "agent_decisions_total",
        "webhook_inbound_total",
    ):
        assert family in body


def test_agent_decision_counter_increments_on_inbound(client, operator_token):
    before = sum(
        sample.value
        for metric in agent_decisions_total.collect()
        for sample in metric.samples
        if sample.name == "agent_decisions_total"
    )
    res = client.post(
        "/api/clinical/simulate-whatsapp",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={"from_phone": "+90 555 444 33 22", "body": "Metrics testi mesaji."},
    )
    assert res.status_code == 200
    after = sum(
        sample.value
        for metric in agent_decisions_total.collect()
        for sample in metric.samples
        if sample.name == "agent_decisions_total"
    )
    assert after > before


def test_webhook_inbound_counter_records_accept_and_duplicate(client):
    payload = {
        "From": "whatsapp:+905558889911",
        "Body": "Metrics duplicate testi.",
        "MessageSid": "SM_METRICS_001",
    }
    res1 = client.post(
        "/api/webhooks/whatsapp",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    res2 = client.post(
        "/api/webhooks/whatsapp",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert res1.status_code == 200 and res2.status_code == 200

    body, _ = render_metrics()
    text = body.decode("utf-8")
    assert 'webhook_inbound_total{outcome="accepted",provider="whatsapp"}' in text
    assert 'webhook_inbound_total{outcome="duplicate",provider="whatsapp"}' in text


def test_http_requests_counter_tracks_status_codes(client, operator_token):
    client.get("/api/clinical/overview", headers={"Authorization": f"Bearer {operator_token}"})
    body, _ = render_metrics()
    text = body.decode("utf-8")
    # The counter must show at least one 200 response on the clinical overview route.
    assert 'http_requests_total{' in text
    assert 'status="200"' in text


def test_json_formatter_emits_extras():
    import logging
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="cognivault.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.request_id = "abc-123"
    record.organization_id = 42
    out = json.loads(formatter.format(record))
    assert out["level"] == "info"
    assert out["logger"] == "cognivault.test"
    assert out["message"] == "hello world"
    assert out["request_id"] == "abc-123"
    assert out["organization_id"] == 42


def test_request_id_header_still_present_after_metrics_middleware(client):
    res = client.get("/healthz", headers={"X-Request-ID": "metrics-test-id"})
    assert res.status_code == 200
    assert res.headers.get("X-Request-ID") == "metrics-test-id"
