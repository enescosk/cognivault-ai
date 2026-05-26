import pytest


def test_branding_endpoints(client, admin_token, operator_token):
    # GET branding as admin
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/clinic/admin/branding", headers=headers)
    assert res.status_code == 200
    assert "branding" in res.json()

    # PATCH branding as admin
    res = client.patch(
        "/api/clinic/admin/branding",
        headers=headers,
        json={
            "headline": "Yeni Diş Kliniği",
            "sub_headline": "Yeni estetik servislerimizle",
            "primary_color": "#ff0000",
        }
    )
    assert res.status_code == 200
    assert res.json()["branding"]["headline"] == "Yeni Diş Kliniği"
    assert res.json()["branding"]["primary_color"] == "#ff0000"

    # Unauthorized access as operator
    op_headers = {"Authorization": f"Bearer {operator_token}"}
    res = client.get("/api/clinic/admin/branding", headers=op_headers)
    assert res.status_code == 403


def test_doctors_crud_endpoints(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create a doctor
    res = client.post(
        "/api/clinic/admin/doctors",
        headers=headers,
        json={"full_name": "Dr. Ahmet Yılmaz", "specialty": "Ortodonti", "is_active": True}
    )
    assert res.status_code == 200
    doctor_id = res.json()["id"]
    assert res.json()["full_name"] == "Dr. Ahmet Yılmaz"

    # 2. Get list of doctors
    res = client.get("/api/clinic/admin/doctors", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 1
    assert any(doc["id"] == doctor_id for doc in res.json())

    # 3. Update the doctor
    res = client.patch(
        f"/api/clinic/admin/doctors/{doctor_id}",
        headers=headers,
        json={"full_name": "Dr. Ahmet Yılmaz Edit", "specialty": "Ortodonti Edit", "is_active": False}
    )
    assert res.status_code == 200
    assert res.json()["full_name"] == "Dr. Ahmet Yılmaz Edit"
    assert not res.json()["is_active"]

    # 4. Delete the doctor
    res = client.delete(f"/api/clinic/admin/doctors/{doctor_id}", headers=headers)
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    # 5. Delete again should return 404
    res = client.delete(f"/api/clinic/admin/doctors/{doctor_id}", headers=headers)
    assert res.status_code == 404


def test_services_crud_endpoints(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create a service
    res = client.post(
        "/api/clinic/admin/services",
        headers=headers,
        json={"name": "Kanal Tedavisi", "description": "Detaylı endodonti hizmeti", "is_active": True}
    )
    assert res.status_code == 200
    service_id = res.json()["id"]
    assert res.json()["name"] == "Kanal Tedavisi"

    # 2. Get list
    res = client.get("/api/clinic/admin/services", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 1

    # 3. Update
    res = client.patch(
        f"/api/clinic/admin/services/{service_id}",
        headers=headers,
        json={"name": "Kanal Tedavisi Edit", "description": "Yeni açıklama", "is_active": True}
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Kanal Tedavisi Edit"

    # 4. Delete
    res = client.delete(f"/api/clinic/admin/services/{service_id}", headers=headers)
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_kvkk_disclosures_endpoints(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Create a KVKK disclosure version
    res = client.post(
        "/api/clinic/admin/disclosures",
        headers=headers,
        json={"version": "v1.0.1", "disclosure_text": "Kişisel verilerin korunması kanunu aydınlatma metni...", "is_active": True}
    )
    assert res.status_code == 200
    disclosure_id = res.json()["id"]
    assert res.json()["version"] == "v1.0.1"

    # 2. Get disclosures list
    res = client.get("/api/clinic/admin/disclosures", headers=headers)
    assert res.status_code == 200
    assert len(res.json()) >= 1
    assert res.json()[0]["id"] == disclosure_id
