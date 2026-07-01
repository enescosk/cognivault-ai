# AI Stack Karar Dokümanı

> **Durum:** Karar verildi (2026-05-25) — kullanıcı onayı alındı.
> **Geçerlilik:** Faz 2 (Local AI Stack Ayağa Kaldırma) için referans.
> **Revize:** İlk benchmark sonuçlarından sonra (Faz 2 sonu).

## Bağlam

CogniVault Clinical, KVKK uyumu için tüm AI işlemeyi **Türkiye sınırlarında, lokal modellerle** yapacak. Bu doküman LLM / STT / TTS / VAD katmanlarının teknoloji seçimini ve gerekçesini sabitler.

## Kararlar

### LLM: Qwen2.5-7B-Instruct + vLLM

**Seçildi.** Alternatifler: Llama 3.1 8B (Ollama), Trendyol-Cosmos-TR, Aya Expanse.

**Gerekçe:**
- **Türkçe performansı:** Qwen2.5 ailesi Türkçe token verimliliği açısından Llama 3.1'den ~%18-25 daha iyi (Türkçe karakterler için tokenizer daha sıkı). Benchmark: Open LLM Leaderboard TR ve OpenETHZ TR-Eval.
- **Tool calling:** Native function calling desteği var (klinik agent'ımızdaki tool sistemiyle uyumlu, [orchestrator.py:744](../backend/app/agent/orchestrator.py:744) refactor'unda OpenAI tool-call interface'i drop-in çalışır).
- **vLLM ile prod throughput:** Ollama dev için iyi ama prod'da PagedAttention + continuous batching gerekiyor. vLLM bir RTX 4090'da 7B modelle ~80-120 req/s sürdürür.
- **VRAM:** 7B INT4/INT8 quantization ile 8GB VRAM yeter; FP16 ile 16GB. RTX 4090 (24GB) ile rahat.
- **Lisans:** Apache 2.0 — ticari kullanım serbest, Llama 3.1 Community License kısıtlarını taşımaz.

**Reddedilen alternatifler:**
- **Llama 3.1 8B:** TR token verimliliği daha düşük, lisansı ticarileşmede dikkat istiyor (700M aktif kullanıcı sınırı şu an alakasız ama gelecekte yumuşatan değil sertleştiren bir madde).
- **Trendyol-Cosmos-TR:** TR fine-tune iyi ama tool calling bozuk; klinik intent classification için doğrudan kullanılamaz.
- **Aya Expanse:** Multilingual harika ama 8B sürümü tool calling'de Qwen2.5'in gerisinde.

**Kısıtlar:**
- İlk deploy'da **8B değil 7B** ile başla — VRAM cebimizi tutar
- Quantization: AWQ veya GPTQ INT4 (kalite kaybı <2%, hız 2x)
- Context window: 32K (default) yeterli; klinik konuşma için çok bol

### STT: Faster-Whisper large-v3-turbo

**Seçildi.** Alternatifler: Whisper.cpp, Vosk-TR, Coqui STT.

**Gerekçe:**
- **TR doğruluğu:** WER ~%6-9 (gürültülü telefon hattında ~%12-15) — OpenAI Whisper-1 ile aynı kalite.
- **Hız:** CTranslate2 backend ile RTX 4090'da real-time 5-7x; CPU'da bile real-time 1.2-1.5x mümkün (low-end fallback).
- **Streaming:** Chunked inference destekli — 200-300ms chunk'larla canlı transcript akışı kurulabilir (telefon latency için kritik).
- **Lisans:** MIT.

**Kısıtlar:**
- Telefon kanalında **8kHz µ-law/A-law** input için preprocessing gerekir (16kHz upsample)
- VAD entegrasyonu zorunlu — yoksa boş ses parçalarını da işliyor

### TTS: Coqui XTTS-v2 (ilk seçim), F5-TTS (yedek)

**Seçildi: XTTS-v2.** Alternatifler: F5-TTS, Kokoro-82M, Piper TR.

**Gerekçe:**
- **TR kalitesi:** XTTS-v2 çok dilli, TR'de doğal prozodi. MOS ~4.1.
- **Speaker cloning:** Klinik kendi sekreterinin sesini referans verirse (6 saniye örnek) o sesi klonlayabilir — pazarlama açısından "klinik kendi sesi" çok güçlü hikaye.
- **Streaming:** Chunked synthesis ile ilk ses chunk'ı <400ms.
- **Lisans:** Coqui Public Model License — **non-commercial**. ⚠️ **Bu ticari ürün için sorun.** Faz 2 başında ticari lisans alınmalı veya alternatife geçilmeli.

**Alternatif: F5-TTS**
- MIT lisans, ticari kullanım serbest
- Speaker cloning kalitesi XTTS'e yakın, biraz daha mekanik
- Streaming desteği daha az olgun

**Karar:** PoC'de XTTS-v2 ile başla (lisans pilot için tolere edilebilir), Faz 5 öncesi F5-TTS'e geçişi karara bağla.

**Kısıtlar:**
- TTS GPU yiyor — LLM ile aynı GPU'da çalışırken bellek yönetimi kritik. Mümkünse ayrı GPU veya CPU inference (yavaş ama olur).

### VAD: silero-vad

**Seçildi.** Alternatifler: WebRTC VAD, py-webrtcvad.

**Gerekçe:**
- ONNX runtime, <50ms inference
- Türkçe konuşmada false positive düşük
- MIT lisans

### Inference Orchestration

| Katman | Servis | Port | GPU? |
|---|---|---|---|
| LLM | vLLM | 8001 | evet (16GB) |
| STT | faster-whisper API (kendi FastAPI wrapper'ı) | 8002 | evet (~3GB) veya CPU |
| TTS | XTTS-v2 server | 8003 | evet (~4GB) |
| VAD | edge (caller tarafında) | inline | CPU |

`docker-compose.local-ai.yml` ile ayağa kalkacak; her servis bağımsız health check, ortak Docker network.

### Donanım hedefi

| Aşama | Donanım | Maliyet |
|---|---|---|
| Geliştirme | Lokal — 1x RTX 4090 24GB veya MacBook M3 Max 64GB | Mevcut |
| Pilot (1-3 klinik) | Bir TR datacenter'da 1x RTX 4090 dedicated sunucu | ~6000-8000 TL/ay |
| Prod (10+ klinik) | 2x RTX 4090 veya 1x A100 40GB; HA için 2 node | ~30000-50000 TL/ay |

### Performans hedefleri

- **Telefon end-to-end latency** (hasta sustu → AI cevap sesi başladı): **<1.2s p50, <2s p95**
- **WhatsApp/web yanıt** (mesaj geldi → AI cevap gönderildi): **<2s p50, <4s p95**
- **STT WER (TR, telefon):** <%12
- **LLM intent classification accuracy** (golden set): **>%92**
- **Throughput:** 50 eşzamanlı konuşma (50 telefon hattı eşdeğeri) pilot kapasitesi

## Bağımlılıklar ve riskler

- **GPU temini:** RTX 4090 TR'de stok dalgalı; Faz 2 öncesi tedarikçi netleştirilmeli
- **vLLM versiyon stabilitesi:** Aktif geliştirilen proje; pin'lenmiş version (`vllm==0.6.3` veya stable LTS) tercih et
- **TTS lisansı:** XTTS-v2 non-commercial — pilot sonrası F5-TTS migration planı önceden hazır olsun
- **Türkçe eval datası:** Henüz yok — Faz 2'de 100+ örnek (telefon transkript + beklenen intent + beklenen cevap) hazırlanmalı

## Sonraki adım

Bu karar dokümanı kabul edildi. **Faz 2 (Local AI Stack)** başlatılınca:
1. `docker-compose.local-ai.yml` PR
2. `backend/app/ai/{llm,stt,tts}/` provider abstraction PR
3. Golden eval seti PR
4. Latency benchmark scripti PR

---

## Ek (2026-07-02): ElevenLabs — opt-in, rıza+DPA kapılı premium ses katmanı

**Karar:** Varsayılan ses yığını yerel kalır (faster-whisper STT + Piper tr_TR TTS; KVKK local-first). ElevenLabs, klinik ödeme istekliliği gösterirse devreye alınacak **opt-in premium katman** olarak konumlanır — hasta sesi/metni yurt dışına çıktığı için sınır-ötesi transfer sayılır ve üç-koşullu rıza kapısı arkasındadır.

**Seçilen ürünler (elevenlabs.io/pricing/api):**
- **TTS (Selin sesi):** Flash / Turbo (`eleven_flash_v2_5`) — ~75ms ultra-düşük gecikme; telefon turn-taking için kritik. Multilingual v2/v3 daha kaliteli ama 250-300ms real-time hissi bozar.
- **STT (hasta konuşması):** Scribe v2 Realtime (`scribe_v2_realtime`) — ~150ms, gerçek-zamanlı, 90+ dil (TR dahil).
- **KULLANILMAYACAK:** ElevenAgents tam pipeline — İP-2 deterministik yönetişim zarfını + kalibre/çekimser triyajı bypass eder (çekirdek farklılaştırıcı + patent istemleri).

**Maliyet hissi:** ~5 turluk çağrı ≈ TTS $0.12 (Flash) + STT $0.03 = **~$0.15/çağrı**; yerel yığın $0. Premium katman yalnızca kalite farkı ödeme istekliliği yarattığında.

**Rıza kapısı (yumuşatılamaz):** `app/ai/voice_factory.py::external_voice_permitted` üç koşulu birden ister: (1) klinik dış-işleme/DPA açık (`voice_external_enabled`), (2) hasta VOICE_RECORDING açık rızası, (3) sağlayıcı API anahtarı. Biri eksikse ses yereldedir. Doğruluk tablosu `app/ai/voice_routing.py` panosunda (8 kombinasyon) kanıtlı; `app.evidence` "Ses-Rıza" panosuna bağlı.

**Uygulanan:** config alanları (`elevenlabs_api_key/tts_model/stt_model/voice_id`), `ElevenLabsTTS` + `ElevenLabsScribeSTT` provider iskeletleri, kapılı routing, `voice_routing` kanıt panosu + 18 test.

**Kalan:** ElevenLabs sözleşmesi/DPA + API anahtarı temini; canlı çağrı yolunun (`public.py`/`voice.py`) per-hasta rızayı `get_stt/tts_provider(consent_granted=...)`'a taşıması; gerçek TR kalite/gecikme A/B ölçümü (yerel vs ElevenLabs).
