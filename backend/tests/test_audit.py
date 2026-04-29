def test_audit_log_created_on_login(client):
    # Successful login should create an audit entry
    client.post("/api/auth/login", json={"email": "admin@test.com", "password": "password123"})
    # Verify via admin endpoint
    token_res = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "password123"})
    token = token_res.json()["access_token"]
    res = client.get("/api/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    logs = res.json()
    assert isinstance(logs, list)
    assert len(logs) > 0


def test_audit_log_on_failed_login(client):
    client.post("/api/auth/login", json={"email": "admin@test.com", "password": "wrongpassword"})
    token_res = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "password123"})
    token = token_res.json()["access_token"]
    res = client.get("/api/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    logs = res.json()
    failure_logs = [l for l in logs if l.get("result_status") == "failure"]
    assert len(failure_logs) > 0


def test_audit_log_not_deletable(client, admin_token):
    # There should be no DELETE endpoint for audit logs
    res = client.delete("/api/audit-logs/1", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code in (404, 405)
