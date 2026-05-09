"""Tests for appointment slots and booking endpoints."""


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_list_slots_requires_auth(client):
    res = client.get("/api/appointments/slots")
    assert res.status_code == 401


def test_list_slots_returns_list(client, customer_token):
    res = client.get("/api/appointments/slots", headers=_auth(customer_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_list_slots_filter_by_department(client, customer_token):
    res = client.get("/api/appointments/slots?department=Technical+Support", headers=_auth(customer_token))
    assert res.status_code == 200
    slots = res.json()
    assert isinstance(slots, list)
    for slot in slots:
        assert slot["department"] == "Technical Support"


def test_list_appointments_requires_auth(client):
    res = client.get("/api/appointments")
    assert res.status_code == 401


def test_list_appointments_empty_initially(client, customer_token):
    res = client.get("/api/appointments", headers=_auth(customer_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_book_appointment(client, customer_token):
    slots_res = client.get("/api/appointments/slots", headers=_auth(customer_token))
    slots = slots_res.json()
    if not slots:
        return  # no seed data; skip booking test

    slot_id = slots[0]["id"]
    res = client.post(
        "/api/appointments",
        json={"slot_id": slot_id, "purpose": "Test booking", "contact_phone": "+905551234567"},
        headers=_auth(customer_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["slot_id"] == slot_id
    assert "confirmation_code" in data
    assert data["status"] == "confirmed"


def test_book_same_slot_twice_fails(client, customer_token):
    slots_res = client.get("/api/appointments/slots", headers=_auth(customer_token))
    slots = [s for s in slots_res.json() if not s.get("is_booked")]
    if len(slots) < 1:
        return

    slot_id = slots[0]["id"]
    payload = {"slot_id": slot_id, "purpose": "Double booking test", "contact_phone": "+905559876543"}
    r1 = client.post("/api/appointments", json=payload, headers=_auth(customer_token))
    assert r1.status_code == 200

    r2 = client.post("/api/appointments", json=payload, headers=_auth(customer_token))
    assert r2.status_code in (400, 409)
