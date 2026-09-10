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
                      "metadata": {"application": "share-my-bread", "kind": "grocery_preference"}},
            )
        self._raise(response)
        return response.json()

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
