"""Billing API — plan kataloğu + aktif abonelik + kullanım kotaları.

Sadece operator/admin görür. Customer rolü bu endpoint'leri çağıramaz.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_organization, get_db, require_roles
from app.models import BillingPlan, Organization, RoleName, User
from app.services.billing_service import (
    ensure_internal_subscription,
    quota_summary,
    seed_billing_plans,
)

router = APIRouter(prefix="/billing", tags=["billing"])


class PlanResponse(BaseModel):
    tier: str
    display_name: str
    monthly_price_usd: float
    max_conversations_per_month: int
    max_voice_minutes_per_month: int
    max_agents: int
    max_llm_cost_usd_per_month: float
    features: dict


@router.get("/plans", response_model=list[PlanResponse])
def list_plans(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles(RoleName.OPERATOR, RoleName.ADMIN)),
) -> list[PlanResponse]:
    seed_billing_plans(db)
    rows = db.scalars(
        select(BillingPlan).where(BillingPlan.is_active == True).order_by(BillingPlan.monthly_price_usd)  # noqa: E712
    ).all()
    return [
        PlanResponse(
            tier=r.tier.value,
            display_name=r.display_name,
            monthly_price_usd=r.monthly_price_usd,
            max_conversations_per_month=r.max_conversations_per_month,
            max_voice_minutes_per_month=r.max_voice_minutes_per_month,
            max_agents=r.max_agents,
            max_llm_cost_usd_per_month=r.max_llm_cost_usd_per_month,
            features=r.features_json or {},
        )
        for r in rows
    ]


@router.get("/subscription")
def get_subscription(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: User = Depends(require_roles(RoleName.OPERATOR, RoleName.ADMIN)),
) -> dict:
    """Aktif aboneliği + bu ayki kullanımı + kotaları döner."""
    # Demo organizasyonlar için INTERNAL plan otomatik garanti edilir.
    ensure_internal_subscription(db, organization.id)
    return quota_summary(db, organization.id)
