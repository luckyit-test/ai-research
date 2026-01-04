"""
Base Agent class - основа для всех AI агентов
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
import json

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


@dataclass
class AgentResult:
    """Результат работы агента"""
    success: bool
    data: Any
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata
        }


class BaseAgent(ABC):
    """
    Базовый класс для всех AI агентов.
    Использует Claude API для выполнения задач.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 0.7
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        if ANTHROPIC_AVAILABLE:
            self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        else:
            self.client = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Имя агента"""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Системный промпт агента"""
        pass

    @abstractmethod
    async def run(self, **kwargs) -> AgentResult:
        """Выполнить задачу агента"""
        pass

    def _call_claude(
        self,
        messages: list[dict],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """Вызов Claude API"""
        if not self.client:
            raise RuntimeError("Anthropic client not initialized")

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            system=system or self.system_prompt,
            messages=messages,
            temperature=self.temperature
        )

        return response.content[0].text

    def _parse_json_response(self, response: str) -> dict:
        """Парсинг JSON из ответа Claude"""
        # Ищем JSON в ответе
        try:
            # Попробуем напрямую
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Ищем JSON блок в markdown
        import re
        json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Ищем просто { ... }
        brace_match = re.search(r'\{[\s\S]*\}', response)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Не удалось распарсить JSON из ответа: {response[:200]}...")


class AgentPipeline:
    """
    Пайплайн для последовательного выполнения агентов.
    """

    def __init__(self, agents: list[BaseAgent]):
        self.agents = agents

    async def run(self, initial_data: dict) -> AgentResult:
        """
        Запускает всех агентов последовательно.
        Каждый агент получает результат предыдущего.
        """
        current_data = initial_data
        results = []

        for agent in self.agents:
            try:
                result = await agent.run(**current_data)
                results.append({
                    "agent": agent.name,
                    "result": result.to_dict()
                })

                if not result.success:
                    return AgentResult(
                        success=False,
                        data=results,
                        error=f"Agent {agent.name} failed: {result.error}"
                    )

                # Обновляем данные для следующего агента
                if isinstance(result.data, dict):
                    current_data.update(result.data)
                else:
                    current_data[agent.name.lower().replace(" ", "_") + "_result"] = result.data

            except Exception as e:
                return AgentResult(
                    success=False,
                    data=results,
                    error=f"Agent {agent.name} raised exception: {str(e)}"
                )

        return AgentResult(
            success=True,
            data=current_data,
            metadata={"pipeline_results": results}
        )
