from __future__ import annotations

import re

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditResultStatus, KnowledgeArticle, User
from app.services.audit_service import log_action
from app.services.enterprise_service import ensure_enterprise_access, get_default_organization


def _clean_tags(tags: list[str]) -> list[str]:
    cleaned: list[str] = []
    for tag in tags:
        value = tag.strip().lower()
        if value and value not in cleaned:
            cleaned.append(value[:40])
    return cleaned[:8]


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[\wçğıöşüÇĞİÖŞÜ]{3,}", text.lower())}


def list_knowledge_articles(db: Session, current_user: User) -> list[KnowledgeArticle]:
    ensure_enterprise_access(current_user)
    organization = get_default_organization(db)
    return list(
        db.scalars(
            select(KnowledgeArticle)
            .where(KnowledgeArticle.organization_id == organization.id, KnowledgeArticle.is_active.is_(True))
            .order_by(KnowledgeArticle.updated_at.desc(), KnowledgeArticle.id.desc())
        )
    )


def create_knowledge_article(
    db: Session,
    *,
    current_user: User,
    title: str,
    content: str,
    tags: list[str],
) -> KnowledgeArticle:
    ensure_enterprise_access(current_user)
    organization = get_default_organization(db)
    article = KnowledgeArticle(
        organization_id=organization.id,
        title=title.strip(),
        content=content.strip(),
        tags=_clean_tags(tags),
    )
    db.add(article)
    db.commit()
    db.refresh(article)

    log_action(
        db,
        user_id=current_user.id,
        action_type="knowledge.article_created",
        explanation="Knowledge article created",
        result_status=AuditResultStatus.SUCCESS,
        details={"article_id": article.id, "title": article.title, "tags": article.tags},
    )
    return article


def search_knowledge_articles(db: Session, current_user: User, query: str, limit: int = 5) -> list[tuple[KnowledgeArticle, int]]:
    ensure_enterprise_access(current_user)
    if not query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Search query is required")

    query_tokens = _tokens(query)
    articles = list_knowledge_articles(db, current_user)
    scored: list[tuple[KnowledgeArticle, int]] = []
    for article in articles:
        title_tokens = _tokens(article.title)
        content_tokens = _tokens(article.content)
        tag_tokens = _tokens(" ".join(article.tags or []))
        score = (len(query_tokens & title_tokens) * 8) + (len(query_tokens & tag_tokens) * 6) + (len(query_tokens & content_tokens) * 3)
        lower_query = query.lower()
        if article.title.lower() in lower_query or any(tag in lower_query for tag in (article.tags or [])):
            score += 8
        if score > 0:
            scored.append((article, min(score, 100)))

    scored.sort(key=lambda item: (item[1], item[0].updated_at), reverse=True)
    return scored[: max(1, min(limit, 10))]
