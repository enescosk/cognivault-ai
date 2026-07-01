"""İP-3.7 — Gerçek-zamanlı ses kontrol katmanı.

Şimdilik: turn-taking + kesinti (barge-in) + endpointing durum makinesi
(`turn_taking.py`). Akustik VAD/DSP (kare enerjisi / konuşma-olasılığı) bu makineye
`is_speech` besler; makine turn kararlarını üretir. DSP entegrasyonu ses altyapısı
gerektirir; kontrol mantığı saf-Python ve deterministiktir.
"""

from app.voice.turn_taking import (  # noqa: F401
    TurnEvent,
    TurnState,
    TurnTakingConfig,
    TurnTakingController,
    build_report,
)
from app.voice.vad import (  # noqa: F401
    EnergyVad,
    EnergyVadConfig,
    rms_dbfs,
    zero_crossing_rate,
)
