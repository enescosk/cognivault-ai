def test_request_id_and_timing_headers_are_added(client):
    res = client.get("/health", headers={"X-Request-ID": "test-request-123"})

    assert res.status_code == 200
    assert res.headers["X-Request-ID"] == "test-request-123"
    assert float(res.headers["X-Process-Time-ms"]) >= 0


def test_validation_errors_use_standard_envelope(client):
    res = client.post("/api/auth/login", json={"email": "not-an-email", "password": ""})

    assert res.status_code == 422
    payload = res.json()
    assert payload["error"]["code"] == "validation_error"
    assert payload["error"]["request_id"]
    assert payload["error"]["path"] == "/api/auth/login"
    assert isinstance(payload["error"]["detail"], list)


def test_unauthorized_errors_use_standard_envelope(client):
    res = client.get("/api/auth/me")

    assert res.status_code == 401
    payload = res.json()
    assert payload["error"]["code"] == "unauthorized"
    assert payload["error"]["message"] == "Authentication required"


def test_readiness_report_exposes_backend_contract(client):
    res = client.get("/health/ready")

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["checks"]["database"]["status"] == "ok"
    assert "llm" in data["checks"]
    assert "voice" in data["checks"]
    assert "security" in data["checks"]


def test_production_runtime_rejects_unsafe_defaults():
    from app.core.config import Settings

    settings = Settings(
        app_env="production",
        jwt_secret="change-me-in-production",
        seed_demo_data=False,
        auto_create_schema=False,
    )

    try:
        settings.validate_runtime_safety()
    except RuntimeError as exc:
        assert "JWT_SECRET" in str(exc)
    else:
        raise AssertionError("production settings accepted the default JWT secret")


def test_production_runtime_requires_explicit_migrations():
    from app.core.config import Settings

    settings = Settings(
        app_env="production",
        jwt_secret="x" * 48,
        seed_demo_data=False,
        auto_create_schema=True,
    )

    try:
        settings.validate_runtime_safety()
    except RuntimeError as exc:
        assert "AUTO_CREATE_SCHEMA" in str(exc)
    else:
        raise AssertionError("production settings accepted startup schema mutation")
