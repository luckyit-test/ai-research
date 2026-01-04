"""
Prompt Optimizer Agent - итеративное улучшение промптов
Оценивает -> Улучшает -> Сравнивает -> Повторяет
"""
from typing import Optional
from dataclasses import dataclass, field
import json

from .base import BaseAgent, AgentResult
from ..config import STYLE_KEYWORDS, NEGATIVE_PROMPTS


@dataclass
class PromptScore:
    """Оценка промпта по критериям"""
    clarity: float = 0.0           # Ясность описания
    photorealism: float = 0.0      # Фотореалистичность
    lighting: float = 0.0          # Качество освещения
    composition: float = 0.0       # Композиция кадра
    face_description: float = 0.0  # Описание лица
    scene_detail: float = 0.0      # Детализация сцены

    @property
    def total(self) -> float:
        """Общий score (0-1)"""
        weights = {
            "clarity": 0.15,
            "photorealism": 0.20,
            "lighting": 0.15,
            "composition": 0.15,
            "face_description": 0.20,
            "scene_detail": 0.15
        }
        return sum(
            getattr(self, k) * v
            for k, v in weights.items()
        )

    def to_dict(self) -> dict:
        return {
            "clarity": self.clarity,
            "photorealism": self.photorealism,
            "lighting": self.lighting,
            "composition": self.composition,
            "face_description": self.face_description,
            "scene_detail": self.scene_detail,
            "total": self.total
        }


@dataclass
class OptimizationResult:
    """Результат одной итерации оптимизации"""
    iteration: int
    original_prompt: str
    improved_prompt: str
    original_score: PromptScore
    improved_score: PromptScore
    improvements_made: list[str]
    is_better: bool


class PromptOptimizerAgent(BaseAgent):
    """
    Агент итеративного улучшения промптов.

    Алгоритм:
    1. Оценить текущий промпт по 6 критериям
    2. Улучшить слабые стороны
    3. Оценить улучшенный промпт
    4. Если улучшение > threshold - принять
    5. Повторить до max_iterations или target_score
    """

    @property
    def name(self) -> str:
        return "Prompt Optimizer"

    @property
    def system_prompt(self) -> str:
        return """You are an expert at optimizing prompts for photorealistic AI image generation.

Your task is to evaluate and improve prompts to generate the BEST possible photorealistic images.

EVALUATION CRITERIA (score each 0-1):
1. clarity (0.15): Is the description clear and unambiguous?
2. photorealism (0.20): Does it specify photorealistic quality markers?
3. lighting (0.15): Is lighting described professionally?
4. composition (0.15): Is the camera angle, framing, and composition specified?
5. face_description (0.20): Is the person's face described in detail for preservation?
6. scene_detail (0.15): Are scene elements detailed enough?

PHOTOREALISTIC REQUIREMENTS:
- Must include: photorealistic, hyperrealistic, 8k uhd, professional photography
- Must specify: lighting type, camera settings, skin texture details
- Must avoid: cartoon, anime, illustration, artistic style keywords
- Format: ALWAYS 16:9 aspect ratio
- Face: Detailed description of facial features for identity preservation

OUTPUT FORMAT (JSON):
{
    "scores": {
        "clarity": 0.8,
        "photorealism": 0.7,
        "lighting": 0.6,
        "composition": 0.75,
        "face_description": 0.85,
        "scene_detail": 0.7
    },
    "weaknesses": ["list of weak points"],
    "improved_prompt": "the improved prompt text",
    "improvements_made": ["list of specific improvements"],
    "reasoning": "why these changes improve the prompt"
}"""

    def __init__(
        self,
        max_iterations: int = 5,
        min_improvement: float = 0.05,
        target_score: float = 0.95,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.max_iterations = max_iterations
        self.min_improvement = min_improvement
        self.target_score = target_score

    async def run(
        self,
        prompt: str,
        face_description: str = "",
        scene_context: str = "",
        num_iterations: Optional[int] = None,
        **kwargs
    ) -> AgentResult:
        """
        Итеративно улучшает промпт.

        Args:
            prompt: Исходный промпт
            face_description: Описание лица пользователя
            scene_context: Контекст сцены из фандома
            num_iterations: Количество итераций (или max_iterations)
        """
        iterations = num_iterations or self.max_iterations
        current_prompt = prompt
        history = []
        best_prompt = prompt
        best_score = 0.0

        for i in range(iterations):
            # Оцениваем и улучшаем
            result = await self._optimize_iteration(
                prompt=current_prompt,
                face_description=face_description,
                scene_context=scene_context,
                iteration=i + 1
            )

            if not result:
                break

            # Сохраняем историю
            history.append({
                "iteration": i + 1,
                "original_prompt": current_prompt,
                "improved_prompt": result["improved_prompt"],
                "original_score": result["original_score"],
                "improved_score": result["improved_score"],
                "improvements": result["improvements_made"],
                "is_better": result["is_better"]
            })

            # Если улучшение существенное - принимаем
            if result["is_better"]:
                improvement = result["improved_score"]["total"] - result["original_score"]["total"]

                if improvement >= self.min_improvement:
                    current_prompt = result["improved_prompt"]

                    if result["improved_score"]["total"] > best_score:
                        best_prompt = result["improved_prompt"]
                        best_score = result["improved_score"]["total"]

            # Достигли целевого score
            if best_score >= self.target_score:
                break

        return AgentResult(
            success=True,
            data={
                "original_prompt": prompt,
                "optimized_prompt": best_prompt,
                "final_score": best_score,
                "iterations_used": len(history),
                "history": history,
                "reached_target": best_score >= self.target_score
            },
            metadata={
                "max_iterations": iterations,
                "target_score": self.target_score
            }
        )

    async def _optimize_iteration(
        self,
        prompt: str,
        face_description: str,
        scene_context: str,
        iteration: int
    ) -> Optional[dict]:
        """Одна итерация оптимизации"""
        try:
            evaluation_prompt = f"""Evaluate and improve this prompt for PHOTOREALISTIC image generation.

CURRENT PROMPT:
{prompt}

FACE DESCRIPTION (must be preserved):
{face_description}

SCENE CONTEXT:
{scene_context}

REQUIRED STYLE KEYWORDS to include:
{', '.join(STYLE_KEYWORDS[:5])}

KEYWORDS TO AVOID:
{', '.join(NEGATIVE_PROMPTS[:5])}

REQUIREMENTS:
- Output MUST be photorealistic (like a professional photograph)
- Format: 16:9 aspect ratio
- Include detailed lighting description
- Preserve face description for identity matching

Evaluate the current prompt, identify weaknesses, and provide an improved version.
Return JSON with scores, weaknesses, improved_prompt, and improvements_made."""

            response = self._call_claude([{"role": "user", "content": evaluation_prompt}])
            result = self._parse_json_response(response)

            # Парсим scores
            scores = result.get("scores", {})
            original_score = PromptScore(
                clarity=scores.get("clarity", 0.5),
                photorealism=scores.get("photorealism", 0.5),
                lighting=scores.get("lighting", 0.5),
                composition=scores.get("composition", 0.5),
                face_description=scores.get("face_description", 0.5),
                scene_detail=scores.get("scene_detail", 0.5)
            )

            improved_prompt = result.get("improved_prompt", prompt)

            # Оцениваем улучшенный промпт
            improved_score = await self._evaluate_prompt(improved_prompt, face_description)

            is_better = improved_score.total > original_score.total

            return {
                "original_score": original_score.to_dict(),
                "improved_score": improved_score.to_dict(),
                "improved_prompt": improved_prompt,
                "improvements_made": result.get("improvements_made", []),
                "weaknesses": result.get("weaknesses", []),
                "is_better": is_better
            }

        except Exception as e:
            print(f"Optimization iteration {iteration} failed: {e}")
            return None

    async def _evaluate_prompt(self, prompt: str, face_description: str) -> PromptScore:
        """Оценивает промпт по критериям"""
        try:
            eval_prompt = f"""Score this prompt for photorealistic image generation (0-1 for each):

PROMPT: {prompt}

FACE TO PRESERVE: {face_description}

Score these criteria:
1. clarity: Is description clear?
2. photorealism: Does it specify photo-quality markers?
3. lighting: Is lighting professional?
4. composition: Is framing/angle specified?
5. face_description: Is face detailed for preservation?
6. scene_detail: Are scene elements detailed?

Return ONLY JSON: {{"clarity": 0.X, "photorealism": 0.X, ...}}"""

            response = self._call_claude([{"role": "user", "content": eval_prompt}])
            scores = self._parse_json_response(response)

            return PromptScore(
                clarity=scores.get("clarity", 0.5),
                photorealism=scores.get("photorealism", 0.5),
                lighting=scores.get("lighting", 0.5),
                composition=scores.get("composition", 0.5),
                face_description=scores.get("face_description", 0.5),
                scene_detail=scores.get("scene_detail", 0.5)
            )
        except Exception:
            return PromptScore()

    def quick_evaluate(self, prompt: str) -> dict:
        """
        Быстрая эвристическая оценка без вызова API.
        Полезно для предварительной фильтрации.
        """
        score = {
            "clarity": 0.5,
            "photorealism": 0.0,
            "lighting": 0.0,
            "composition": 0.0,
            "face_description": 0.0,
            "scene_detail": 0.5
        }

        prompt_lower = prompt.lower()

        # Photorealism check
        photo_keywords = ["photorealistic", "hyperrealistic", "photograph", "8k", "uhd", "dslr"]
        score["photorealism"] = min(1.0, sum(0.2 for kw in photo_keywords if kw in prompt_lower))

        # Lighting check
        lighting_keywords = ["lighting", "light", "shadow", "cinematic", "golden hour", "soft light"]
        score["lighting"] = min(1.0, sum(0.2 for kw in lighting_keywords if kw in prompt_lower))

        # Composition check
        composition_keywords = ["close-up", "medium shot", "wide shot", "portrait", "angle", "framing"]
        score["composition"] = min(1.0, sum(0.2 for kw in composition_keywords if kw in prompt_lower))

        # Face description check
        face_keywords = ["eyes", "face", "skin", "hair", "expression", "features"]
        score["face_description"] = min(1.0, sum(0.2 for kw in face_keywords if kw in prompt_lower))

        # Negative check (reduce score if anime/cartoon keywords present)
        for neg in NEGATIVE_PROMPTS:
            if neg in prompt_lower:
                score["photorealism"] = max(0, score["photorealism"] - 0.3)

        # Calculate total
        weights = {"clarity": 0.15, "photorealism": 0.20, "lighting": 0.15,
                   "composition": 0.15, "face_description": 0.20, "scene_detail": 0.15}
        score["total"] = sum(score[k] * weights[k] for k in weights)

        return score

    def ensure_photorealistic(self, prompt: str) -> str:
        """
        Гарантирует фотореалистичные ключевые слова в промпте.
        """
        prompt_lower = prompt.lower()

        # Добавляем обязательные ключевые слова если их нет
        additions = []

        if "photorealistic" not in prompt_lower and "hyperrealistic" not in prompt_lower:
            additions.append("photorealistic")

        if "8k" not in prompt_lower and "uhd" not in prompt_lower:
            additions.append("8k uhd")

        if "lighting" not in prompt_lower:
            additions.append("cinematic lighting")

        if additions:
            prompt = f"{prompt}, {', '.join(additions)}"

        # Добавляем negative prompt
        prompt = f"{prompt} --no {', '.join(NEGATIVE_PROMPTS[:5])}"

        return prompt
