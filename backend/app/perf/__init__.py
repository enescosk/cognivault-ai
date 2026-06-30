"""İP-3 — On-prem yerel yığın başarım (performans) ölçüm paketi.

Yerel yığının her istekte sunucuda koşan saf-Python kritik yolunu (PII maskeleme
→ yönetişim zarfı → niyet/triyaj) deterministik biçimde benchmark'lar ve modest
donanım gecikme bütçelerine göre kapı uygular. Model aşamaları (ASR/LLM/TTS) için
belgeli bütçe hedefleri taşır. Klinik kalite panosuyla (İP-1.8) birleşince
İP-3.9 "gecikme + kalite raporu" çıktısını verir.
"""
