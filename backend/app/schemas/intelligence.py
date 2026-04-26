from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IntelligenceSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    base_url: str | None = None
    is_active: bool
    requires_api_key: bool
    rate_limit_per_minute: int
    policy: dict
    created_at: datetime


class IntelligenceJobCreateRequest(BaseModel):
    source_kind: str = Field(default="manual", examples=["manual", "google_places", "reddit_api"])
    query: str = Field(min_length=2, max_length=500)
    target_location: str | None = Field(default=None, max_length=160)
    max_results: int = Field(default=10, ge=1, le=50)
    seed_text: str | None = Field(
        default=None,
        max_length=8000,
        description="Optional user-provided text to parse in local/manual mode.",
    )


class LeadContactPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    value: str
    label: str | None = None
    normalized_value: str
    is_primary: bool
    confidence: int
    source_url: str | None = None
    created_at: datetime


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    organization_name: str
    description: str | None = None
    location: str | None = None
    source_url: str | None = None
    source_kind: str
    confidence: int
    consent_basis: str
    provenance: dict
    contact_points: list[LeadContactPointResponse] = []
    created_at: datetime
    updated_at: datetime


class IntelligenceJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: IntelligenceSourceResponse
    query: str
    target_location: str | None = None
    status: str
    max_results: int
    summary: str | None = None
    error_message: str | None = None
    metadata_json: dict
    leads: list[LeadResponse] = []
    created_at: datetime
    updated_at: datetime


class OutreachDraftCreateRequest(BaseModel):
    lead_id: int
    channel: str = Field(default="phone", pattern="^(phone|email|social|crm)$")
    intent: str = Field(default="intro", max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class OutreachDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    channel: str
    subject: str | None = None
    body: str
    status: str
    metadata_json: dict
    created_at: datetime
    updated_at: datetime
