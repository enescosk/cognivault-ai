# Dental AI Secretary Golden Research Findings

Date: 2026-05-25

This file preserves the working research notes for the CogniVault dental AI receptionist product. Treat it as product discovery evidence, not as legal, medical, or patent advice.

## Product Thesis

Dental clinics need a 24/7 AI receptionist that handles phone, WhatsApp, and web chat without behaving like a generic chatbot. The assistant must understand colloquial Turkish dental complaints, route them to the right specialty, collect only the minimum appointment data, and escalate medical, insurance, identity, or emergency situations to a human review queue.

The strongest product direction is a KVKK-first hybrid architecture:

- Deterministic guardrails decide what may be automated.
- LLM/voice models provide empathy, summarization, and natural dialogue.
- Clinical and privacy gates always win over generated text.
- PMS/HBYS write-back happens only after policy, consent, and slot checks.
- Doctor approval packets preserve audit evidence without exposing unnecessary patient data.

## Patient Profiles And Conversation Strategy

| Patient profile | Patient state | Typical expression | AI strategy | Empathetic reply pattern |
| --- | --- | --- | --- | --- |
| Acute pain or urgent dental patient | High anxiety, pain, panic | "Dün geceden beri dişim zonkluyor, yanağım şişti. Hemen gelebilir miyim?" | Detect urgency, avoid diagnosis, route to priority slot or human review. | "Çok geçmiş olsun. Ağrı ve şişlik bilgisini öncelikli not aldım. Size en yakın uygun slotu kontrol ederken, şikayet hızla artıyorsa insan operatöre de öncelikli aktarıyorum." |
| Dental anxiety patient | Fear, avoidance, trust gap | "İmplant istiyorum ama acı duyacağımdan çok korkuyorum." | Normalize fear, explain comfort workflow, collect appointment intent. | "Bu kaygıyı yaşamanız çok anlaşılır. Hekim görüşmesinde konfor seçeneklerini özellikle not düşeceğim. Ön görüşme için size uygun gün/saat nedir?" |
| Financial or insurance concern | Cost sensitivity | "Kanal tedavisi fiyatı ne kadar, sigortam karşılar mı?" | Give non-binding scope, block exact insurance lookup until consent/human review. | "Fiyat işlem ve hekim planına göre netleşir. Sigorta kontrolü için açık onay ve doğrulama gerekeceği için bunu güvenli şekilde operatör ekranına düşürüyorum." |
| Time-constrained patient | Impatient, scheduling focus | "Sadece akşam 6'dan sonra gelebilirim." | Offer narrow slots, avoid too many questions. | "Yoğun temponuzu anlıyorum. Akşam saatleri için iki uygun alternatif kontrol ediyorum: 18:15 veya 18:45 size uyar mı?" |
| Cancellation or reschedule | Low commitment or guilt | "Yarın gelemeyeceğim, iptal edelim." | Confirm request, protect continuity by offering reschedule. | "Tabii, randevunuzu güncelleyebilirim. Tedaviniz aksamaması için haftaya aynı gün/saat aralığına bakmamı ister misiniz?" |

## Core Capabilities

- Real-time voice intake with low latency.
- Turkish colloquial dental complaint routing.
- Endodonti, Periodontoloji, Pedodonti, Ortodonti, İmplantoloji, Ağız/Diş/Çene Cerrahisi, Estetik Diş Hekimliği mapping.
- Emergency and risk phrase detection.
- Insurance and identity lookup blocking until explicit consent and human review.
- KVKK local-first deployment mode.
- Hybrid deployment mode only with explicit consent and processor review.
- PMS/HBYS write-back after deterministic policy checks.
- Doctor approval packets for uncertain, risky, or regulated responses.
- Audit log with redacted previews and selected processing mode.
- Recall/reactivation campaign engine for missed or overdue appointments.

## KVKK Design Notes

Health complaints are special category personal data. Voice interaction metadata, identifiers, phone numbers, appointment history, insurance details, and free-text health complaints must be treated with separate sensitivity levels.

Implementation defaults:

- Store and process production health data in Turkey or on-premise by default.
- Block cross-border AI processors unless explicit consent, processor registry, and legal review are present.
- Keep external LLM, STT, and TTS processors disabled for clinical data by default, even when API keys exist in the environment.
- Store redacted previews in operator queues where possible.
- Do not ask for TCKN, card number, or insurance member details in an automated reply.
- Do not give diagnosis or treatment instructions.
- Require human review for emergency, insurance, national identifier, low-confidence, and frustration events.

Official sources to keep near the compliance review:

- KVKK special category data guide: https://www.kvkk.gov.tr/Icerik/8184/Ozel-Nitelikli-Kisisel-Verilerin-Islenmesine-Iliskin-Rehber
- KVKK cross-border transfer undertaking notes: https://www.kvkk.gov.tr/Icerik/6741/YURT-DISINA-KISISEL-VERI-AKTARIMINDA-HAZIRLANACAK-TAAHHUTNAMELERDE-DIKKAT-EDILMESI-GEREKEN-HUSUSLARA-ILISKIN-DUYURU
- TÜRKPATENT patent and utility model guide: https://www.turkpatent.gov.tr/basvuru-kilavuzlari

## Candidate Patent Direction

The product should not be framed as "an AI receptionist" only. That is too broad. The protectable direction should focus on a technical method:

1. Real-time Turkish dental complaint normalization.
2. Specialty-specific deterministic routing.
3. KVKK-aware data classification.
4. Consent and residency policy gating.
5. Redacted doctor approval packet generation.
6. PMS write-back only after all gates pass.

Potential invention title:

"KVKK-first multimodal dental AI receptionist with deterministic clinical governance and appointment write-back"

Evidence to preserve:

- This research file.
- Scenario tables.
- Routing keyword taxonomy.
- Backend governance metadata examples.
- Safety-gate tests.
- UX screenshots and demo flows.
- Patent novelty search results.

## Product Roadmap

1. Harden clinical governance: data class detection, residency mode, explicit consent gates, human review triggers.
2. Improve voice UX: natural Turkish TTS, interruption handling, VAD tuning, background noise tolerance.
3. Build deep PMS layer: slot lookup, patient card creation, appointment write-back, cancellation, reschedule.
4. Add recall engine: missed appointment follow-up, six-month hygiene recall, post-treatment check-in.
5. Add compliance console: processor registry, retention settings, consent log, audit export.
6. Prepare patent package: novelty search, claim drafting, flow diagrams, evidence bundle.
