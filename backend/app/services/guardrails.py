"""Check-only NeMo boundary; never generates a shopping response or executes tools."""
import asyncio
from functools import lru_cache
from pathlib import Path

from app.shared.config import get_settings

CONFIG_PATH = Path(__file__).resolve().parents[2] / 'guardrails' / 'shopping'


class GuardrailUnavailable(Exception):
    def __init__(self):
        super().__init__('Safety checks are unavailable. Please try again.')


class NeMoChecker:
    def __init__(self, engine, timeout=15):
        self.engine = engine
        self.timeout = timeout

    async def check(self, stage, text):
        if stage not in {'input', 'output'} or not text.strip():
            raise GuardrailUnavailable()
        try:
            # A single role selects only that direction, never full agent generation.
            result = await asyncio.wait_for(self.engine.check_async(messages=[{
                'role': 'user' if stage == 'input' else 'assistant', 'content': text,
            }]), timeout=self.timeout)
            status = getattr(result.status, 'value', result.status).lower()
            if status not in {'passed', 'modified', 'blocked'}:
                raise GuardrailUnavailable()
            if status == 'blocked':
                return {'status': 'blocked', 'text': ''}
            if not isinstance(result.content, str) or not result.content.strip():
                raise GuardrailUnavailable()
            return {'status': status, 'text': result.content}
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
        return NeMoChecker(engine)
    except Exception:
        raise GuardrailUnavailable() from None
