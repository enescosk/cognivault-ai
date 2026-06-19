from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger("cognivault.ai_factory")
MAX_MODEL_JSON_CHARS = 64_000


def parse_model_json(content: str) -> dict[str, Any] | None:
    """Parse a bounded JSON object, tolerating the common fenced-JSON format."""
    if not isinstance(content, str):
        return None
    raw = content.strip()
    if not raw or len(raw) > MAX_MODEL_JSON_CHARS:
        return None
    if raw.startswith("```"):
        lines = raw.splitlines()
        if len(lines) < 3 or not lines[-1].strip().startswith("```"):
            return None
        raw = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _record_telemetry(model: str, prompt_t: int, completion_t: int, org_id: int | None = None) -> None:
    try:
        from app.db.session import SessionLocal
        from app.services.llm_usage import record_llm_usage
        db = SessionLocal()
        try:
            record_llm_usage(
                db,
                model=model,
                prompt_tokens=prompt_t,
                completion_tokens=completion_t,
                agent_type="clinical_triage",
                organization_id=org_id,
            )
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Failed to record LLM telemetry: {e}")


class LLMProvider(ABC):
    @abstractmethod
    def generate_chat_reply(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 600,
        organization_id: int | None = None,
    ) -> dict[str, Any] | None:
        """
        Sends the messages to the LLM and returns a parsed JSON response.
        Should return None or raise an exception if the model call fails or returns invalid JSON.
        """
        pass


class OpenAIProvider(LLMProvider):
    def generate_chat_reply(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 600,
        organization_id: int | None = None,
    ) -> dict[str, Any] | None:
        settings = get_settings()
        if not settings.openai_api_key:
            return None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.openai_api_key)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            
            # Telemetry
            usage = getattr(response, "usage", None)
            if usage:
                prompt_t = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_t = int(getattr(usage, "completion_tokens", 0) or 0)
                _record_telemetry(settings.openai_model, prompt_t, completion_t, organization_id)

            content = response.choices[0].message.content or ""
            return parse_model_json(content)
        except Exception as e:
            logger.error(f"OpenAIProvider error: {e}")
            return None


class AnthropicProvider(LLMProvider):
    def generate_chat_reply(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 600,
        organization_id: int | None = None,
    ) -> dict[str, Any] | None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            return None
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=settings.anthropic_api_key)
            messages = [{"role": "user", "content": prompt}]
            kwargs: dict[str, Any] = {
                "model": settings.anthropic_model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": messages,
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = client.messages.create(**kwargs)
            
            # Telemetry
            usage = getattr(response, "usage", None)
            if usage:
                prompt_t = int(getattr(usage, "input_tokens", 0) or 0)
                completion_t = int(getattr(usage, "output_tokens", 0) or 0)
                _record_telemetry(settings.anthropic_model, prompt_t, completion_t, organization_id)

            content = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
            return parse_model_json(content)
        except Exception as e:
            logger.error(f"AnthropicProvider error: {e}")
            return None


class LocalQwenProvider(LLMProvider):
    """
    Local Qwen2.5-7B-Instruct provider running via vLLM or Ollama on http://localhost:8001.
    If the endpoint is not reachable (e.g. in offline testing), it falls back to a mock structured generator.
    """
    def generate_chat_reply(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.2,
        max_tokens: int = 600,
        organization_id: int | None = None,
    ) -> dict[str, Any] | None:
        settings = get_settings()
        url = settings.local_llm_base_url.rstrip("/") + "/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": settings.local_llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=settings.local_llm_timeout) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                content = res_data["choices"][0]["message"]["content"]
                return parse_model_json(content)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            logger.warning(f"Local Qwen endpoint connection failed: {e}. Falling back to structured mock parser.")
            return self._generate_mock_reply(prompt)
        except Exception as e:
            logger.error(f"LocalQwenProvider unhandled error: {e}")
            return None

    def _generate_mock_reply(self, prompt: str) -> dict[str, Any]:
        """
        Parses keys/intents from the prompt and generates a structured JSON response
        similar to what Qwen2.5 would output, enabling offline testing.
        """
        from app.services.customer_understanding import understand_primary_intent

        if "<patient_message>" in prompt:
            patient_message = prompt.rsplit("<patient_message>", 1)[-1].split("</patient_message>", 1)[0].strip()
        else:
            patient_message = prompt.rsplit("Patient message:", 1)[-1].strip()
        understanding = understand_primary_intent(patient_message)
        intent = understanding.intent
        confidence = understanding.confidence
        action = "collect_info"
        reply = "Ben Selin. Size nasıl yardımcı olabilirim?"

        if intent == "book_appointment":
            reply = "Diş şikayetiniz için en uygun randevu saatlerini kontrol ediyorum. Hangi gün uygun olursunuz?"
            action = "collect_appointment_details"
        elif intent == "ask_price":
            reply = "Tedavi fiyatlarımız işlem türüne göre değişmektedir. Hangi işlem hakkında fiyat almak istiyorsunuz?"
        elif intent == "medical_emergency":
            reply = "Bu durum acil olabilir. Lütfen 112'yi arayın veya en yakın acil servise başvurun."
            action = "emergency_guidance"
        elif intent == "reschedule_appointment":
            reply = "Randevunuzu değiştirebilirim. Mevcut tarih ile tercih ettiğiniz yeni zamanı paylaşır mısınız?"
            action = "collect_reschedule_details"
        elif intent == "cancel_appointment":
            reply = "İptal işlemi için randevu tarihinizi paylaşır mısınız?"
            action = "collect_cancellation_details"

        return {
            "reply": reply,
            "confidence": confidence,
            "intent": intent,
            "action": action,
            "requires_human_review": intent in ("medical_emergency", "ask_insurance"),
            "risk_reason": "emergency_guardrail" if intent == "medical_emergency" else None,
            "data": {}
        }


def get_llm_provider(data_residency_mode: str, external_transfer_allowed: bool) -> LLMProvider:
    """
    Returns the appropriate LLM provider based on KVKK data residency settings.
    """
    if data_residency_mode == "tr_local_first" and not external_transfer_allowed:
        return LocalQwenProvider()
    
    # Fallback/hybrid modes
    settings = get_settings()
    if settings.anthropic_api_key:
        return AnthropicProvider()
    elif settings.openai_api_key:
        return OpenAIProvider()
    
    # Ultimate local fallback
    return LocalQwenProvider()
