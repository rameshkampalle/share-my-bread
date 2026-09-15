import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.guardrails import router, get_checker
from app.services.guardrails import NeMoChecker, GuardrailUnavailable
from app.shared.config import Settings


class CheckerTests(unittest.IsolatedAsyncioTestCase):
    async def test_input_modified_text_is_returned(self):
        engine = SimpleNamespace(check_async=AsyncMock(return_value=SimpleNamespace(status='modified', content='Find bread')))
        result = await NeMoChecker(engine).check('input', 'Find bread private email')
        self.assertEqual(result, {'status': 'modified', 'text': 'Find bread'})

    async def test_unknown_or_empty_decisions_fail_closed(self):
        for status, content in [('unknown', 'text'), ('passed', '')]:
            engine = SimpleNamespace(check_async=AsyncMock(return_value=SimpleNamespace(status=status, content=content)))
            with self.assertRaises(GuardrailUnavailable):
                await NeMoChecker(engine).check('input', 'Find bread')

    async def test_exceptions_hide_provider_details(self):
        engine = SimpleNamespace(check_async=AsyncMock(side_effect=RuntimeError('secret diagnostic')))
        with self.assertRaises(GuardrailUnavailable) as error:
            await NeMoChecker(engine).check('input', 'Find bread')
        self.assertNotIn('secret diagnostic', str(error.exception))

    async def test_timeout_fails_closed(self):
        async def slow(**kwargs):
            await asyncio.sleep(1)
        with self.assertRaises(GuardrailUnavailable):
            await NeMoChecker(SimpleNamespace(check_async=slow), timeout=0.001).check('input', 'Find bread')


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.checker = SimpleNamespace(check=AsyncMock(return_value={'status': 'passed', 'text': 'Find bread'}))
        self.app.dependency_overrides[get_checker] = lambda: self.checker
        self.settings = patch('app.api.guardrails.get_settings', return_value=Settings(guardrails_api_secret='test-only-secret'))
        self.settings.start()
        self.addCleanup(self.settings.stop)
        self.client = TestClient(self.app)

    def test_missing_or_wrong_service_secret_rejected(self):
        for headers in [{}, {'X-Guardrails-Secret': 'wrong'}]:
            response = self.client.post('/api/guardrails/check', headers=headers, json={'stage': 'input', 'text': 'Find bread'})
            self.assertEqual(response.status_code, 401)
        self.checker.check.assert_not_called()

    def test_missing_service_configuration_fails_closed(self):
        with patch("app.api.guardrails.get_settings", return_value=Settings()):
            response = self.client.post("/api/guardrails/check", json={"stage": "input", "text": "Find bread"})
            self.assertEqual(response.status_code, 503)
        self.checker.check.assert_not_called()

    def test_valid_request_checks_content(self):
        response = self.client.post('/api/guardrails/check', headers={'X-Guardrails-Secret': 'test-only-secret'}, json={'stage': 'input', 'text': 'Find bread'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'passed')

    def test_bad_stage_and_blank_text_rejected(self):
        for payload in [{'stage': 'tool', 'text': 'Find bread'}, {'stage': 'input', 'text': ' '}]:
            response = self.client.post('/api/guardrails/check', headers={'X-Guardrails-Secret': 'test-only-secret'}, json=payload)
            self.assertEqual(response.status_code, 422)
        self.checker.check.assert_not_called()

    def test_checker_failure_returns_generic_503(self):
        self.checker.check.side_effect = GuardrailUnavailable()
        response = self.client.post('/api/guardrails/check', headers={'X-Guardrails-Secret': 'test-only-secret'}, json={'stage': 'input', 'text': 'Find bread'})
        self.assertEqual(response.status_code, 503)

    def test_catalogue_requires_service_authentication(self):
        with patch('app.api.guardrails.checked_catalogue', AsyncMock()) as catalogue:
            self.assertEqual(self.client.post('/api/guardrails/catalogue', json={'productIds': []}).status_code, 401)
        catalogue.assert_not_called()

    def test_catalogue_rejects_untrusted_fields_invalid_ids_and_large_batches(self):
        valid_id = '10000000-0000-0000-0000-000000000001'
        for payload in [{'productIds': ['not-a-uuid']}, {'productIds': [valid_id] * 11}, {'productIds': [], 'price': 0}]:
            with patch('app.api.guardrails.checked_catalogue', AsyncMock()) as catalogue:
                response = self.client.post('/api/guardrails/catalogue', headers={'X-Guardrails-Secret': 'test-only-secret'}, json=payload)
            self.assertEqual(response.status_code, 422)
            catalogue.assert_not_called()
