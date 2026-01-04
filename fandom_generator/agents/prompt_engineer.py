"""
Prompt Engineer Agent - создает детальные промпты для генерации
Четвертый агент в пайплайне
"""
from typing import Optional
from dataclasses import dataclass

from .base import BaseAgent, AgentResult


@dataclass
class GenerationPrompt:
    """Промпт для генерации изображения"""
    scene_id: int
    main_prompt: str
    negative_prompt: str
    midjourney_params: str
    niji_params: str
    style_reference_notes: str
    character_reference_notes: str


class PromptEngineerAgent(BaseAgent):
    """
    Агент-инженер промптов.
    Создает оптимизированные промпты для Midjourney/Niji.
    """

    @property
    def name(self) -> str:
        return "Prompt Engineer"

    @property
    def system_prompt(self) -> str:
        return """You are an expert prompt engineer for Midjourney and Niji image generation.

Your task is to create highly optimized prompts that:
1. Maintain the user's facial identity (through --cref and detailed descriptions)
2. Match the fandom's visual style perfectly
3. Create stunning, high-quality images
4. Include proper technical parameters

PROMPT STRUCTURE for maximum face similarity:
1. Start with the person description (face features, expression)
2. Add the scene context
3. Include style and lighting
4. Add technical parameters

KEY TECHNIQUES for face preservation:
- Always use --cref [photo_url] --cw 80-100 for character reference
- Include detailed face description in the prompt
- Use "person with [face features]" not just "person"
- Specify viewing angle that matches the reference photo

For ANIME fandoms (Niji mode):
- Use --niji 6 --style expressive or cute
- Adapt face description to anime conventions
- Keep key identifying features

For LIVE-ACTION fandoms (Midjourney mode):
- Use --style raw for photorealism
- Lower stylize (--s 50-100) for face accuracy
- Emphasize photorealistic skin, eyes, lighting

Output as JSON:
{
    "prompts": [
        {
            "scene_id": 1,
            "main_prompt": "full prompt text",
            "face_integration": "how face description is integrated",
            "style_keywords": ["key", "style", "words"],
            "technical_params": {
                "midjourney": "--ar 16:9 --style raw --s 50 --cref URL --cw 100",
                "niji": "--niji 6 --ar 16:9 --style expressive --cref URL --cw 80"
            },
            "negative_prompt": "things to avoid",
            "quality_notes": "notes about expected quality"
        }
    ],
    "global_recommendations": {
        "best_mode": "niji|midjourney",
        "cref_weight": 80,
        "sref_weight": 40,
        "aspect_ratio": "16:9"
    }
}"""

    async def run(
        self,
        scenes_data: dict,
        face_data: dict,
        universe_data: dict,
        **kwargs
    ) -> AgentResult:
        """
        Создает промпты для каждой сцены.

        Args:
            scenes_data: Данные о сценах от Scene Architect
            face_data: Данные о лице от Face Analyzer
            universe_data: Данные о вселенной от Universe Researcher
        """
        try:
            scenes = scenes_data.get("scenes", [])
            style_type = universe_data.get("style_type", "mixed")

            # Получаем описание лица
            face_description = face_data.get("enhanced_description", {}).get(
                "face_description",
                face_data.get("basic_description", "a person")
            )

            # Ключевые особенности для сохранения
            key_features = face_data.get("enhanced_description", {}).get(
                "key_features",
                []
            )

            # Стилевые рекомендации из universe_data
            style_guide = universe_data.get("prompt_style_guide", {})
            style_keywords = style_guide.get("style_keywords", [])

            prompt = f"""Create optimized prompts for these scenes:

FACE DESCRIPTION (CRITICAL - must be preserved):
{face_description}

KEY IDENTIFYING FEATURES:
{', '.join(key_features) if key_features else 'standard features'}

UNIVERSE STYLE:
Type: {style_type}
Style Keywords: {', '.join(style_keywords)}

SCENES:
{self._format_scenes(scenes)}

Create prompts that:
1. ALWAYS include the face description naturally
2. Match the {style_type} visual style
3. Include proper Midjourney/Niji parameters
4. Optimize for face similarity with --cref --cw parameters
"""

            response = self._call_claude([{"role": "user", "content": prompt}])
            prompts_data = self._parse_json_response(response)

            # Добавляем глобальные рекомендации
            prompts_data["generation_config"] = {
                "use_niji": style_type in ["anime", "animated"],
                "use_face_swap": True,  # Всегда используем face swap для максимального сходства
                "cref_weight": 80 if style_type in ["anime", "animated"] else 100,
                "target_similarity": 0.75
            }

            return AgentResult(
                success=True,
                data=prompts_data,
                metadata={
                    "num_prompts": len(prompts_data.get("prompts", [])),
                    "style_type": style_type
                }
            )

        except Exception as e:
            return AgentResult(
                success=False,
                data=None,
                error=str(e)
            )

    def _format_scenes(self, scenes: list) -> str:
        """Форматирует сцены для промпта"""
        formatted = []
        for scene in scenes:
            formatted.append(f"""
Scene {scene.get('id', 'N/A')}: {scene.get('title', 'Untitled')}
- Description: {scene.get('description', '')}
- Location: {scene.get('location', '')}
- Mood: {scene.get('mood', '')}
- Lighting: {scene.get('lighting', '')}
- Camera: {scene.get('camera_angle', '')}
- User Role: {scene.get('user_role', '')}
- Action: {scene.get('action', '')}
""")
        return "\n".join(formatted)

    def enhance_prompt_for_face(self, prompt: str, face_description: str) -> str:
        """
        Улучшает промпт для лучшего сохранения лица.
        Вспомогательный метод для постобработки.
        """
        # Убеждаемся что описание лица в начале
        if face_description.lower() not in prompt.lower():
            # Вставляем описание лица после первого существительного
            words = prompt.split()
            insert_pos = 0
            for i, word in enumerate(words):
                if word.lower() in ["a", "an", "the"]:
                    insert_pos = i + 2
                    break

            words.insert(insert_pos, f"({face_description})")
            prompt = " ".join(words)

        return prompt
