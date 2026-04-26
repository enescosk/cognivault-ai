from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.models import User
from app.schemas.knowledge import KnowledgeArticleCreateRequest, KnowledgeArticleResponse, KnowledgeSearchResult
from app.services.knowledge_service import create_knowledge_article, list_knowledge_articles, search_knowledge_articles


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/articles", response_model=list[KnowledgeArticleResponse])
def get_articles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[KnowledgeArticleResponse]:
    return [KnowledgeArticleResponse.model_validate(item) for item in list_knowledge_articles(db, current_user)]


@router.post("/articles", response_model=KnowledgeArticleResponse)
def post_article(
    payload: KnowledgeArticleCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeArticleResponse:
    return KnowledgeArticleResponse.model_validate(
        create_knowledge_article(
            db,
            current_user=current_user,
            title=payload.title,
            content=payload.content,
            tags=payload.tags,
        )
    )


@router.get("/search", response_model=list[KnowledgeSearchResult])
def search_articles(
    q: str = Query(min_length=2),
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[KnowledgeSearchResult]:
    return [
        KnowledgeSearchResult(**KnowledgeArticleResponse.model_validate(article).model_dump(), score=score)
        for article, score in search_knowledge_articles(db, current_user, q, limit)
    ]
