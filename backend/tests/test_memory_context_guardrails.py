import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory import router
from app.shared.auth import get_current_user


class MemoryScopeTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id='authenticated-user')
        self.client = TestClient(app)

    def test_no_consent_never_queries_memory_provider(self):
        with patch('app.api.memory.consent_for', AsyncMock(return_value=False)), patch('app.api.memory.Mem0Memory') as memory:
            self.assertEqual(self.client.get('/api/memory/context?query=bread').json(), {'memories': []})
        memory.assert_not_called()

    def test_caller_cannot_select_another_memory_owner(self):
        service = SimpleNamespace(enabled=True, search=AsyncMock(return_value=[{'memory': 'Prefers rye'}]))
        with patch('app.api.memory.consent_for', AsyncMock(return_value=True)) as consent, patch('app.api.memory.Mem0Memory', return_value=service):
            result = self.client.get('/api/memory/context?query=bread&userId=other-user')
        self.assertEqual(result.json(), {'memories': ['Prefers rye']})
        consent.assert_awaited_once_with('authenticated-user')
        service.search.assert_awaited_once_with('authenticated-user', 'bread')
