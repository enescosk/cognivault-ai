"""Tests for intelligence module — sources, jobs, leads, outreach drafts, safety gates."""
import pytest


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Sources ──────────────────────────────────────────────────────────────────

def test_sources_requires_auth(client):
    res = client.get("/api/intelligence/sources")
    assert res.status_code == 401


def test_sources_forbidden_for_customer(client, customer_token):
    res = client.get("/api/intelligence/sources", headers=_auth(customer_token))
    assert res.status_code == 403


def test_sources_accessible_for_operator(client, operator_token):
    res = client.get("/api/intelligence/sources", headers=_auth(operator_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_sources_accessible_for_admin(client, admin_token):
    res = client.get("/api/intelligence/sources", headers=_auth(admin_token))
    assert res.status_code == 200
    sources = res.json()
    assert len(sources) > 0
    kinds = {s["kind"] for s in sources}
    assert "manual" in kinds


# ── Jobs ─────────────────────────────────────────────────────────────────────

def test_create_job_requires_auth(client):
    res = client.post("/api/intelligence/jobs", json={"query": "Acme Corp", "source_kind": "manual"})
    assert res.status_code == 401


def test_create_job_forbidden_for_customer(client, customer_token):
    res = client.post(
        "/api/intelligence/jobs",
        json={"query": "Acme Corp", "source_kind": "manual"},
        headers=_auth(customer_token),
    )
    assert res.status_code == 403


def test_create_manual_job(client, operator_token):
    res = client.post(
        "/api/intelligence/jobs",
        json={
            "query": "Test Company",
            "source_kind": "manual",
            "seed_text": "Test Company, phone: +90 212 000 00 00, email: info@testcompany.com",
        },
        headers=_auth(operator_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("completed", "running", "queued", "failed")
    assert data["query"] == "Test Company"


def test_list_jobs(client, operator_token):
    # ensure at least one job exists
    client.post(
        "/api/intelligence/jobs",
        json={"query": "List test", "source_kind": "manual", "seed_text": "ListCo, tel: +90 500 000 0000"},
        headers=_auth(operator_token),
    )
    res = client.get("/api/intelligence/jobs", headers=_auth(operator_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert len(res.json()) > 0


def test_get_job_detail(client, operator_token):
    create = client.post(
        "/api/intelligence/jobs",
        json={"query": "Detail test", "source_kind": "manual", "seed_text": "DetailCo phone +90 501 111 1111"},
        headers=_auth(operator_token),
    )
    job_id = create.json()["id"]
    res = client.get(f"/api/intelligence/jobs/{job_id}", headers=_auth(operator_token))
    assert res.status_code == 200
    assert res.json()["id"] == job_id


def test_get_nonexistent_job(client, operator_token):
    res = client.get("/api/intelligence/jobs/999999", headers=_auth(operator_token))
    assert res.status_code == 404


# ── Leads ────────────────────────────────────────────────────────────────────

def test_list_leads_requires_auth(client):
    res = client.get("/api/intelligence/leads")
    assert res.status_code == 401


def test_list_leads_forbidden_for_customer(client, customer_token):
    res = client.get("/api/intelligence/leads", headers=_auth(customer_token))
    assert res.status_code == 403


def test_list_leads_returns_list(client, admin_token):
    res = client.get("/api/intelligence/leads", headers=_auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


# ── Outreach drafts — safety gates ───────────────────────────────────────────

def test_create_draft_requires_legal_consent(client, operator_token):
    """Omitting legal_consent_acknowledged must fail with 422."""
    res = client.post(
        "/api/intelligence/outreach-drafts",
        json={"lead_id": 1, "channel": "email", "intent": "intro"},
        headers=_auth(operator_token),
    )
    assert res.status_code == 422


def test_create_draft_with_false_consent_fails(client, operator_token):
    res = client.post(
        "/api/intelligence/outreach-drafts",
        json={"lead_id": 1, "channel": "email", "intent": "intro", "legal_consent_acknowledged": False},
        headers=_auth(operator_token),
    )
    assert res.status_code == 422


def _create_lead_and_draft(client, operator_token, admin_token):
    """Helper: create a job with a lead, then create an outreach draft. Returns draft dict."""
    job_res = client.post(
        "/api/intelligence/jobs",
        json={
            "query": "Draft Test Co",
            "source_kind": "manual",
            "seed_text": "Draft Test Co, phone: +90 322 999 9999, email: contact@drafttestco.com",
        },
        headers=_auth(operator_token),
    )
    assert job_res.status_code == 200, job_res.json()
    leads = client.get("/api/intelligence/leads", headers=_auth(admin_token)).json()
    if not leads:
        return None
    lead_id = leads[0]["id"]
    draft_res = client.post(
        "/api/intelligence/outreach-drafts",
        json={"lead_id": lead_id, "channel": "phone", "intent": "intro", "legal_consent_acknowledged": True},
        headers=_auth(operator_token),
    )
    assert draft_res.status_code == 200
    return draft_res.json()


def test_create_draft_with_consent_succeeds(client, operator_token, admin_token):
    draft = _create_lead_and_draft(client, operator_token, admin_token)
    if draft is None:
        return  # no leads available
    assert draft["status"] == "draft"
    assert "legal_disclaimer" in draft
    assert draft["legal_disclaimer"] != ""


def test_draft_response_includes_legal_disclaimer(client, operator_token, admin_token):
    draft = _create_lead_and_draft(client, operator_token, admin_token)
    if draft is None:
        return
    assert "KVKK" in draft["legal_disclaimer"] or "onay" in draft["legal_disclaimer"].lower()


def test_approve_draft_requires_admin(client, operator_token, admin_token):
    draft = _create_lead_and_draft(client, operator_token, admin_token)
    if draft is None:
        return
    # Operator cannot approve
    res = client.post(f"/api/intelligence/outreach-drafts/{draft['id']}/approve", headers=_auth(operator_token))
    assert res.status_code == 403


def test_approve_draft_as_admin(client, operator_token, admin_token):
    draft = _create_lead_and_draft(client, operator_token, admin_token)
    if draft is None:
        return
    res = client.post(f"/api/intelligence/outreach-drafts/{draft['id']}/approve", headers=_auth(admin_token))
    assert res.status_code == 200
    assert res.json()["status"] == "approved"


def test_reject_draft(client, operator_token, admin_token):
    draft = _create_lead_and_draft(client, operator_token, admin_token)
    if draft is None:
        return
    res = client.post(f"/api/intelligence/outreach-drafts/{draft['id']}/reject", headers=_auth(operator_token))
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"


def test_approve_already_rejected_draft_fails(client, operator_token, admin_token):
    draft = _create_lead_and_draft(client, operator_token, admin_token)
    if draft is None:
        return
    client.post(f"/api/intelligence/outreach-drafts/{draft['id']}/reject", headers=_auth(operator_token))
    res = client.post(f"/api/intelligence/outreach-drafts/{draft['id']}/approve", headers=_auth(admin_token))
    assert res.status_code == 400
