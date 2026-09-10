import unittest
from unittest.mock import patch

from app.services.memory import Mem0Memory, MemoryUnavailable


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, *, post=None, get=None):
        self.post_responses = list(post or [])
        self.get_responses = list(get or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        return self.post_responses.pop(0)

    async def get(self, *_args, **_kwargs):
        return self.get_responses.pop(0)


class MemoryServiceTests(unittest.IsolatedAsyncioTestCase):
    def service(self):
        service = Mem0Memory.__new__(Mem0Memory)
        service.enabled = True
        service.api_key = "test-key"
        return service

    async def test_add_waits_for_successful_mem0_event(self):
        clients = [
            FakeClient(post=[FakeResponse(202, {"event_id": "evt-1", "status": "PENDING"})]),
            FakeClient(get=[
                FakeResponse(200, {"event_id": "evt-1", "status": "RUNNING"}),
                FakeResponse(200, {"event_id": "evt-1", "status": "SUCCEEDED"}),
            ]),
        ]
        with patch("app.services.memory.httpx.AsyncClient", side_effect=clients), patch(
            "app.services.memory.asyncio.sleep", return_value=None
        ):
            result = await self.service().add("user-1", "oat milk")
        self.assertEqual(result["status"], "SUCCEEDED")

    async def test_add_accepts_synchronous_non_inferred_result(self):
        client = FakeClient(post=[FakeResponse(200, {"status": "SUCCEEDED", "results": [{"id": "memory-1"}]})])
        with patch("app.services.memory.httpx.AsyncClient", return_value=client):
            result = await self.service().add("user-1", "oat milk")
        self.assertEqual(result["results"][0]["id"], "memory-1")

    async def test_add_surfaces_failed_mem0_event(self):
        clients = [
            FakeClient(post=[FakeResponse(202, {"event_id": "evt-2", "status": "PENDING"})]),
            FakeClient(get=[FakeResponse(200, {"event_id": "evt-2", "status": "FAILED"})]),
        ]
        with patch("app.services.memory.httpx.AsyncClient", side_effect=clients):
            with self.assertRaisesRegex(MemoryUnavailable, "could not save"):
                await self.service().add("user-1", "Greek yogurt")

    async def test_add_rejects_missing_event_id(self):
        with patch(
            "app.services.memory.httpx.AsyncClient",
            return_value=FakeClient(post=[FakeResponse(202, {"status": "PENDING"})]),
        ):
            with self.assertRaisesRegex(MemoryUnavailable, "tracking event"):
                await self.service().add("user-1", "oat milk")


if __name__ == "__main__":
    unittest.main()
