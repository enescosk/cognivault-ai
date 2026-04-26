from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeArticleCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    content: str = Field(min_length=12)
    tags: list[str] = Field(default_factory=list, max_length=8)


class KnowledgeArticleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    title: str
    content: str
    tags: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchResult(KnowledgeArticleResponse):
    score: int
