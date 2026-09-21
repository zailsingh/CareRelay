import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.schemas.ask import ProviderOutput


class AIProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class AIContext:
    question: str
    deterministic_answer: str
    facts: dict
    safety_note: str


class AIProvider(ABC):
    name: str
    model: str

    @abstractmethod
    async def generate(self, context: AIContext) -> ProviderOutput:
        raise NotImplementedError


class MockAIProvider(AIProvider):
    name = "mock"

    def __init__(self, model: str = "mock-care-relay-v1") -> None:
        self.model = model

    async def generate(self, context: AIContext) -> ProviderOutput:
        return ProviderOutput(answer=context.deterministic_answer)


class OpenRouterAIProvider(AIProvider):
    name = "openrouter"

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key or not model:
            raise ValueError("OpenRouter requires an API key and explicit model ID")
        self.api_key = api_key
        self.model = model

    async def generate(self, context: AIContext) -> ProviderOutput:
        prompt = {
            "question": context.question,
            "verified_facts": context.facts,
            "draft_answer": context.deterministic_answer,
            "safety_note": context.safety_note,
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "Summarize only supplied verified facts. Do not diagnose or "
                                    "prescribe. Do not invent facts or add numbers. "
                                    "Return JSON with one key: answer."
                                ),
                            },
                            {"role": "user", "content": json.dumps(prompt)},
                        ],
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return ProviderOutput.model_validate_json(content)
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValidationError,
            ValueError,
        ) as exc:
            raise AIProviderError(
                "The configured AI provider returned an invalid response"
            ) from exc


def build_ai_provider(configured: Settings) -> AIProvider:
    if configured.ai_provider == "mock":
        return MockAIProvider(configured.ai_model)
    return OpenRouterAIProvider(configured.openrouter_api_key, configured.ai_model)


def get_ai_provider() -> AIProvider:
    return build_ai_provider(get_settings())
