"""İP-R — API öncesi karşılama (reception) katmanı.

Hasta ile ilk temasta, yapısal API/klinik triyaj katmanına inmeden devreye giren
karşılama motoru. Her karşılama biçimini tanır, üsluba/dile aynalanan sıcak yanıt
üretir ve gerçek talebi yutmadan aşağı katmana devreder.
"""

from app.reception.greeting import (  # noqa: F401
    GreetingAnalysis,
    ReceptionTurn,
    analyze_greeting,
    build_report,
    compose_reception,
    synthetic_corpus,
    time_greeting,
)
