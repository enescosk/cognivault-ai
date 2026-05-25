"""Agent context — tüm agent fonksiyonlarının paylaştığı runtime durumu.

Ayrı dosyada tutuluyor ki:
  - parsing/classify/llm modülleri orchestrator'ı import etmeden context'e erişebilsin
  - circular import'lardan kaçınılsın
  - test'ler hafif AgentContext fixtureleri üretebilsin
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import ChatSession, User


@dataclass
class AgentContext:
    db: Session
    user: User
    session: ChatSession
