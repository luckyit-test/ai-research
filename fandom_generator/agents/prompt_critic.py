"""
Prompt Critic Agent - критикует и улучшает промпты
Пятый агент в пайплайне
"""
from typing import Optional
from dataclasses import dataclass

from .base import BaseAgent, AgentResult


@dataclass
class CritiqueResult:
    """Результат критики промпта"""
    scene_id: int
    original_prompt: str
    improved_prompt: str
    score: float  # 0-1
    issues_found: list[str]
    improvements_made: list[str]


class PromptCriticAgent(BaseAgent):
    """
    Агент-критик промптов.
    Анализирует промпты на соответствие требованиям и улучшает их.
    """

    @property
    def name(self) -> str:
        return "Prompt Critic"

    @property
    def system_prompt(self) -> str:
        return """You are a harsh but constructive critic of AI image generation prompts.

Your task is to analyze prompts and identify issues that could result in:
1. Poor face similarity (CRITICAL)
2. Incorrect visual style for the fandom
3. Bad lighting or composition
4. Narrative inconsistencies (hero with villain friendly)
5. Technical issues with Midjourney/Niji parameters

CRITICAL CHECKS:
1. FACE PRESERVATION:
   - Is face description detailed and specific?
   - Is --cref parameter present with appropriate --cw weight?
   - Will the face be visible and prominent in the composition?

2. STYLE CONSISTENCY:
   - Does the prompt match the fandom's visual style?
   - Are style keywords appropriate for the universe?
   - Is the mode (Niji vs Midjourney) correct for the style?

3. NARRATIVE LOGIC:
   - Good and evil are NEVER shown as friends
   - User is in appropriate role for the scene
   - Scene makes sense within the universe

4. LIGHTING & COMPOSITION:
   - Lighting matches the mood
   - Camera angle allows face visibility
   - Composition is aesthetically pleasing

5. TECHNICAL QUALITY:
   - Correct aspect ratio
   - Appropriate stylize level
   - No conflicting parameters

Score each prompt 0-1 and provide specific improvements.

Output as JSON:
{
    "critiques": [
        {
            "scene_id": 1,
            "original_score": 0.6,
            "issues": [
                {
                    "category": "face_preservation|style|narrative|lighting|technical",
                    "severity": "critical|major|minor",
                    "description": "What's wrong",
                    "fix": "How to fix it"
                }
            ],
            "improved_prompt": "The improved prompt text",
            "improved_params": "--corrected --params",
            "final_score": 0.9,
            "confidence": 0.85
        }
    ],
    "overall_assessment": {
        "average_initial_score": 0.6,
        "average_final_score": 0.9,
        "common_issues": ["list of recurring issues"],
        "recommendations": ["general recommendations"]
    }
}"""

    def __init__(
        self,
        min_acceptable_score: float = 0.85,
        max_iterations: int = 3,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.min_acceptable_score = min_acceptable_score
        self.max_iterations = max_iterations

    async def run(
        self,
        prompts_data: dict,
        face_data: dict,
        universe_data: dict,
        scenes_data: dict,
        **kwargs
    ) -> AgentResult:
        """
        Критикует и улучшает промпты.

        Args:
            prompts_data: Промпты от Prompt Engineer
            face_data: Данные о лице
            universe_data: Данные о вселенной
            scenes_data: Данные о сценах
        """
        try:
            prompts = prompts_data.get("prompts", [])
            style_type = universe_data.get("style_type", "mixed")

            # Контекст для критики
            context = f"""
FACE DESCRIPTION (must be preserved):
{face_data.get('basic_description', '')}

UNIVERSE STYLE: {style_type}
KEY STYLE ELEMENTS: {universe_data.get('prompt_style_guide', {}).get('style_keywords', [])}

NARRATIVE RULES:
- Good vs Evil must be clearly separated
- User should be in heroic roles
- Scenes must be logically consistent
"""

            # Итеративное улучшение
            current_prompts = prompts
            iteration = 0
            all_critiques = []

            while iteration < self.max_iterations:
                critique_prompt = f"""{context}

PROMPTS TO CRITIQUE (Iteration {iteration + 1}):
{self._format_prompts_for_critique(current_prompts)}

Analyze each prompt and provide specific improvements.
Focus on:
1. Face preservation (--cref, face description)
2. Style consistency with {style_type}
3. Narrative logic
4. Lighting and composition
5. Technical parameters

Only pass prompts with score >= {self.min_acceptable_score}
"""

                response = self._call_claude([{"role": "user", "content": critique_prompt}])
                critique_data = self._parse_json_response(response)

                all_critiques.append({
                    "iteration": iteration + 1,
                    "critiques": critique_data.get("critiques", [])
                })

                # Проверяем средний score
                critiques = critique_data.get("critiques", [])
                avg_score = sum(c.get("final_score", 0) for c in critiques) / len(critiques) if critiques else 0

                if avg_score >= self.min_acceptable_score:
                    break

                # Обновляем промпты для следующей итерации
                current_prompts = [
                    {
                        **p,
                        "main_prompt": c.get("improved_prompt", p.get("main_prompt")),
                        "technical_params": {
                            **p.get("technical_params", {}),
                            "updated": c.get("improved_params", "")
                        }
                    }
                    for p, c in zip(current_prompts, critiques)
                ]

                iteration += 1

            # Финальный результат
            final_prompts = []
            for prompt, critique in zip(current_prompts, critique_data.get("critiques", [])):
                final_prompts.append({
                    **prompt,
                    "main_prompt": critique.get("improved_prompt", prompt.get("main_prompt")),
                    "critique_score": critique.get("final_score", 0),
                    "issues_fixed": [i.get("description") for i in critique.get("issues", [])]
                })

            return AgentResult(
                success=True,
                data={
                    "final_prompts": final_prompts,
                    "critique_history": all_critiques,
                    "iterations_needed": iteration + 1,
                    "final_average_score": avg_score,
                    "overall_assessment": critique_data.get("overall_assessment", {})
                },
                metadata={
                    "min_score_threshold": self.min_acceptable_score,
                    "passed_threshold": avg_score >= self.min_acceptable_score
                }
            )

        except Exception as e:
            return AgentResult(
                success=False,
                data=None,
                error=str(e)
            )

    def _format_prompts_for_critique(self, prompts: list) -> str:
        """Форматирует промпты для критики"""
        formatted = []
        for p in prompts:
            params = p.get("technical_params", {})
            formatted.append(f"""
Scene {p.get('scene_id', 'N/A')}:
Prompt: {p.get('main_prompt', '')}
MJ Params: {params.get('midjourney', '')}
Niji Params: {params.get('niji', '')}
""")
        return "\n---\n".join(formatted)

    def quick_check(self, prompt: str, style_type: str) -> dict:
        """
        Быстрая проверка промпта без полной критики.
        Полезно для валидации перед генерацией.
        """
        issues = []
        score = 1.0

        # Проверяем наличие --cref
        if "--cref" not in prompt and "cref" not in prompt.lower():
            issues.append("Missing --cref parameter for character reference")
            score -= 0.2

        # Проверяем режим для стиля
        if style_type == "anime" and "--niji" not in prompt:
            issues.append("Anime fandom should use --niji mode")
            score -= 0.1

        if style_type == "live_action" and "--niji" in prompt:
            issues.append("Live-action fandom should not use --niji mode")
            score -= 0.1

        # Проверяем aspect ratio
        if "--ar" not in prompt:
            issues.append("Missing aspect ratio parameter")
            score -= 0.05

        return {
            "score": max(0, score),
            "issues": issues,
            "passed": score >= 0.7
        }
