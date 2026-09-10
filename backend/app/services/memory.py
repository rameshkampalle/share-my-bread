import asyncio
import time

import httpx

from app.domain.memory_policy import scoped_user_id
from app.shared.config import get_settings


class MemoryUnavailable(RuntimeError):
    pass


class Mem0Memory:
    base_url = "https://api.mem0.ai"

    def __init__(self):
        settings = get_settings()
        self.enabled = settings.mem0_enabled and bool(settings.mem0_api_key)
        self.api_key = settings.mem0_api_key

    def _headers(self) -> dict[str, str]:
        if not self.enabled or not self.api_key:
            raise MemoryUnavailable("Preference memory is not configured.")
        return {"Authorization": f"Token {self.api_key}", "Content-Type": "application/json"}

    async def list_memories(self, user_id: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/v3/memories/?page=1&page_size=50", headers=self._headers(),
                json={"filters": {"user_id": scoped_user_id(user_id)}, "fields": ["id", "memory", "created_at"]},
            )
        self._raise(response)
        return response.json().get("results", [])

    async def search(self, user_id: str, query: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{self.base_url}/v3/memories/search/", headers=self._headers(),
                json={"query": query, "filters": {"user_id": scoped_user_id(user_id)}, "top_k": 5},
            )
        self._raise(response)
        return response.json().get("results", [])

    async def add(self, user_id: str, preference: str) -> dict:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self.base_url}/v3/memories/add/", headers=self._headers(),
                json={"messages": [{"role": "user", "content": f"My grocery preference is: {preference}"}],
                      "user_id": scoped_user_id(user_id),
                      # The user has already supplied an explicit fact. Store it directly so the
                      # request is deterministic and does not depend on Mem0's extraction queue.
                      "infer": False,
                      "metadata": {"application": "share-my-bread", "kind": "grocery_preference"}},
            )
        self._raise(response)
        result = response.json()
        if str(result.get("status", "")).upper() == "SUCCEEDED":
            return result
        event_id = result.get("event_id")
        if not event_id:
            raise MemoryUnavailable("Mem0 did not return a tracking event for the preference.")
        return await self.wait_for_event(str(event_id))

    async def wait_for_event(self, event_id: str, timeout_seconds: float = 25) -> dict:
        """Wait until Mem0's asynchronous V3 add pipeline has really persisted the memory."""
        deadline = time.monotonic() + timeout_seconds
        async with httpx.AsyncClient(timeout=15) as client:
            while time.monotonic() < deadline:
                response = await client.get(f"{self.base_url}/v1/event/{event_id}/", headers=self._headers())
                self._raise(response)
                event = response.json()
                status = str(event.get("status", "")).upper()
                if status == "SUCCEEDED":
                    return event
                if status == "FAILED":
                    raise MemoryUnavailable("Mem0 could not save the preference.")
                await asyncio.sleep(0.5)
        raise MemoryUnavailable("Mem0 is still processing the preference. Please try again shortly.")

    async def delete(self, user_id: str, memory_id: str) -> None:
        memories = await self.list_memories(user_id)
        if memory_id not in {str(item.get("id")) for item in memories}:
            raise KeyError(memory_id)
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.delete(
                f"{self.base_url}/v1/memories/{memory_id}/",
                headers=self._headers(),
                params={"delete_linked": "true"},
            )
        self._raise(response)
        # Mem0 deletion can take a moment to become visible through the V3 list API.
        # Do not report success until the memory is actually gone.
        for _ in range(20):
            if memory_id not in {str(item.get("id")) for item in await self.list_memories(user_id)}:
                return
            await asyncio.sleep(0.5)
        raise MemoryUnavailable("Mem0 accepted the deletion but the preference is still visible. Please retry.")

    async def delete_all(self, user_id: str) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.delete(
                f"{self.base_url}/v1/memories", headers=self._headers(), params={"user_id": scoped_user_id(user_id)}
            )
        self._raise(response)

    @staticmethod
    def _raise(response: httpx.Response) -> None:
        if response.status_code >= 400:
            raise MemoryUnavailable(f"Mem0 request failed with status {response.status_code}.")
