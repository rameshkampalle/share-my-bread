"""Check-only NeMo boundary; never generates a shopping response or executes tools."""
import asyncio
from functools import lru_cache
from pathlib import Path

from app.shared.config import get_settings
from app.domain.guardrail_input import mask_sensitive, normalize_input, obvious_override

CONFIG_PATH = Path(__file__).resolve().parents[2] / 'guardrails' / 'shopping'


class GuardrailUnavailable(Exception):
    def __init__(self):
        super().__init__('Safety checks are unavailable. Please try again.')


class NeMoChecker:
    def __init__(self, engine, timeout=15, retrieval_engine=None):
        self.engine = engine
        self.retrieval_engine = retrieval_engine
        self.timeout = timeout

    async def check(self, stage, text):
        if stage not in {'input', 'output', 'retrieval'} or not text.strip():
            raise GuardrailUnavailable()
        original = text
        if stage in {'input', 'retrieval'}:
            text = normalize_input(text)
            if obvious_override(text, retrieved=stage == 'retrieval'):
                return {'status': 'blocked', 'text': ''}
            text = mask_sensitive(text)
        if len(text) > 16000:
            raise GuardrailUnavailable()
        try:
            engine = self.retrieval_engine if stage == 'retrieval' else self.engine
            if engine is None:
                raise GuardrailUnavailable()
            # A single role selects only that direction, never full agent generation.
            result = await asyncio.wait_for(engine.check_async(messages=[{
                'role': 'assistant' if stage == 'output' else 'user', 'content': text,
            }]), timeout=self.timeout)
            status = getattr(result.status, 'value', result.status).lower()
            if status not in {'passed', 'modified', 'blocked'}:
                raise GuardrailUnavailable()
            if status == 'blocked':
                return {'status': 'blocked', 'text': ''}
            if not isinstance(result.content, str) or not result.content.strip():
                raise GuardrailUnavailable()
            return {'status': 'modified' if result.content != original else status, 'text': result.content}
        except Exception:
            # Do not log message bodies, credentials, or provider diagnostics.
            raise GuardrailUnavailable() from None


@lru_cache(maxsize=1)
def build_checker():
    settings = get_settings()
    if not settings.guardrails_gemini_api_key:
        raise GuardrailUnavailable()
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from nemoguardrails import RailsConfig
        from nemoguardrails.rails.llm.llmrails import LLMRails

        config = RailsConfig.from_path(str(CONFIG_PATH))
        judge = ChatGoogleGenerativeAI(
            model=settings.guardrails_model,
            google_api_key=settings.guardrails_gemini_api_key,
            temperature=0, max_retries=0, timeout=10,
        )
        engine = LLMRails(config, llm=judge)
        retrieval_engine = LLMRails(RailsConfig.from_path(str(CONFIG_PATH.parent / 'retrieval')), llm=judge)
        return NeMoChecker(engine, retrieval_engine=retrieval_engine)
    except Exception:
        raise GuardrailUnavailable() from None
