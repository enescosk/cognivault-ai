def test_quality_report_requires_auth(client):
    res = client.get("/api/quality/report")
    assert res.status_code == 401


def test_quality_report_contains_self_improvement_signals(client, admin_token):
    res = client.get("/api/quality/report", headers={"Authorization": f"Bearer {admin_token}"})

    assert res.status_code == 200
    data = res.json()
    assert data["score"] > 0
    assert data["metrics"]["automated_scenarios"] >= 5
    assert any(item["id"] == "noisy_tr_appointment" for item in data["scenarios"])
    assert data["recommendations"]
    assert data["latest_eval"] is None
    assert data["metrics"]["eval_total"] == 0
    assert "feedback_backlog" in data["metrics"]
    assert "llm" in data
    assert "voice" in data


def test_operator_can_submit_quality_feedback(client, operator_token):
    res = client.post(
        "/api/quality/feedback",
        headers={"Authorization": f"Bearer {operator_token}"},
        json={
            "scenario_id": "clinic_whatsapp_edge",
            "signal": "Hasta hem randevu hem fiyat soruyor.",
            "expected_behavior": "Fiyat sorusunu yanıtla, randevu icin eksik bilgileri topla.",
            "severity": "medium",
        },
    )

    assert res.status_code == 200
    assert res.json()["accepted"] is True


def test_customer_quality_feedback_is_read_only(client, customer_token):
    res = client.post(
        "/api/quality/feedback",
        headers={"Authorization": f"Bearer {customer_token}"},
        json={
            "scenario_id": "customer_edge",
            "signal": "Musteri kafasi karisik.",
            "expected_behavior": "Operator incelesin.",
            "severity": "low",
        },
    )

    assert res.status_code == 200
    assert res.json()["accepted"] is False
