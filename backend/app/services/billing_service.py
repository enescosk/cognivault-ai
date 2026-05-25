"""Billing & subscription quota servisi.

Plan kataloğunu seed eder, organizasyon başına aktif aboneliği döner,
kullanım kotalarını hesaplar. Stripe entegrasyonu sonraki adım — şimdilik
internal manuel yönetim için yeterli yüzey.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BillingPlan,
    BillingPlanTier,
    LlmUsageRecord,
    Subscription,
    SubscriptionStatus,
)


# Plan kataloğu — fiyat veya kota değişince yeni `BillingPlan` satırı eklenir,
# eski satır is_active=False yapılır. Tarihsel `Subscription` ler eski plana sabit.
PLAN_CATALOG = [
    {
        "tier": BillingPlanTier.STARTER,
        "display_name": "Starter",
        "monthly_price_usd": 49.0,
        "max_conversations_per_month": 500,
        "max_voice_minutes_per_month": 60,
        "max_agents": 1,
        "max_llm_cost_usd_per_month": 25.0,
        "features_json": {"sso": False, "baa": False, "white_label": False},
    },
    {
        "tier": BillingPlanTier.GROWTH,
        "display_name": "Growth",
        "monthly_price_usd": 199.0,
        "max_conversations_per_month": 5000,
        "max_voice_minutes_per_month": 600,
        "max_agents": 5,
        "max_llm_cost_usd_per_month": 200.0,
        "features_json": {"sso": False, "baa": False, "white_label": False},
    },
    {
        "tier": BillingPlanTier.ENTERPRISE,
        "display_name": "Enterprise",
        "monthly_price_usd": 999.0,
        "max_conversations_per_month": 100000,
        "max_voice_minutes_per_month": 10000,
        "max_agents": 50,
        "max_llm_cost_usd_per_month": 5000.0,
        "features_json": {"sso": True, "baa": True, "white_label": True},
    },
    {
        "tier": BillingPlanTier.INTERNAL,
        "display_name": "Internal / Demo",
        "monthly_price_usd": 0.0,
        "max_conversations_per_month": 999999,
        "max_voice_minutes_per_month": 999999,
        "max_agents": 999,
        "max_llm_cost_usd_per_month": 999999.0,
        "features_json": {"sso": True, "baa": True, "white_label": True, "internal": True},
    },
]


def seed_billing_plans(db: Session) -> None:
    """İdempotent — eksik plan satırlarını ekler, var olanlara dokunmaz."""
    existing = {row.tier for row in db.scalars(select(BillingPlan)).all()}
    for spec in PLAN_CATALOG:
        if spec["tier"] in existing:
            continue
        db.add(BillingPlan(**spec))
    db.commit()


def get_active_subscription(db: Session, organization_id: int) -> Subscription | None:
    """Organizasyonun aktif (ACTIVE veya TRIAL) aboneliğini döner."""
    return db.scalars(
        select(Subscription)
        .where(Subscription.organization_id == organization_id)
        .where(Subscription.status.in_((SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL)))
        .order_by(Subscription.created_at.desc())
        .limit(1)
    ).first()


def ensure_internal_subscription(db: Session, organization_id: int) -> Subscription:
    """Demo/test organizasyonları için INTERNAL plan aboneliği garanti eder.

    Var olan aboneliği bulur ya da INTERNAL plan ile yeni TRIAL satır oluşturur.
    """
    sub = get_active_subscription(db, organization_id)
    if sub is not None:
        return sub
    internal_plan = db.scalars(
        select(BillingPlan).where(BillingPlan.tier == BillingPlanTier.INTERNAL)
    ).first()
    if internal_plan is None:
        seed_billing_plans(db)
        internal_plan = db.scalars(
            select(BillingPlan).where(BillingPlan.tier == BillingPlanTier.INTERNAL)
        ).first()
    sub = Subscription(
        organization_id=organization_id,
        plan_id=internal_plan.id,
        status=SubscriptionStatus.TRIAL,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def quota_summary(db: Session, organization_id: int) -> dict:
    """Mevcut ayki kullanım vs plan kotaları — dashboard kartı için."""
    sub = get_active_subscription(db, organization_id)
    if sub is None:
        return {"subscribed": False}

    plan = db.get(BillingPlan, sub.plan_id)
    if plan is None:
        return {"subscribed": True, "plan_missing": True}

    # Ayın başı → şimdi penceresi
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Aylık LLM maliyeti — LlmUsageRecord'tan agreger
    llm_cost = db.execute(
        select(func.coalesce(func.sum(LlmUsageRecord.estimated_cost_usd), 0.0))
        .where(LlmUsageRecord.organization_id == organization_id)
        .where(LlmUsageRecord.created_at >= period_start)
    ).scalar() or 0.0

    return {
        "subscribed": True,
        "plan": {
            "tier": plan.tier.value,
            "display_name": plan.display_name,
            "monthly_price_usd": plan.monthly_price_usd,
        },
        "status": sub.status.value,
        "period_start": period_start.isoformat(),
        "period_end": (period_start + timedelta(days=31)).isoformat(),
        "usage": {
            "llm_cost_usd": round(float(llm_cost), 4),
        },
        "limits": {
            "max_conversations_per_month": plan.max_conversations_per_month,
            "max_voice_minutes_per_month": plan.max_voice_minutes_per_month,
            "max_agents": plan.max_agents,
            "max_llm_cost_usd_per_month": plan.max_llm_cost_usd_per_month,
        },
        "percent_used": {
            "llm_cost": round(
                (float(llm_cost) / plan.max_llm_cost_usd_per_month * 100.0)
                if plan.max_llm_cost_usd_per_month
                else 0.0,
                1,
            ),
        },
    }
