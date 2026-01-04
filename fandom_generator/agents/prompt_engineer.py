"""
Prompt Engineer Agent - создает детальные ФОТОРЕАЛИСТИЧНЫЕ промпты
ВСЕГДА фотореалистичный стиль, формат 16:9
"""
from typing import Optional
from dataclasses import dataclass

from .base import BaseAgent, AgentResult
from ..config import STYLE_KEYWORDS, NEGATIVE_PROMPTS


@dataclass
class GenerationPrompt:
    """Промпт для генерации изображения"""
    scene_id: int
    main_prompt: str
    negative_prompt: str
    nano_banana_params: dict
    style_notes: str


class PromptEngineerAgent(BaseAgent):
    """
    Агент-инженер промптов.
    Создает ФОТОРЕАЛИСТИЧНЫЕ промпты для Nano Banana 3 Pro.
    ВСЕГДА формат 16:9.
    """

    @property
    def name(self) -> str:
        return "Prompt Engineer"

    @property
    def system_prompt(self) -> str:
        return """You are an expert prompt engineer for PHOTOREALISTIC AI image generation.

CRITICAL REQUIREMENTS:
1. ALL outputs must be PHOTOREALISTIC - like professional photography
2. Format is ALWAYS 16:9 aspect ratio
3. Even for anime/cartoon fandoms (Naruto, Dragon Ball), create PHOTOREALISTIC versions
4. Face preservation is the TOP priority

PROMPT STRUCTURE for photorealistic output:
1. Start with "Photorealistic photograph of [person with face features]"
2. Add the scene context from the fandom
3. Include professional lighting description
4. Add camera and technical details
5. End with quality keywords

MANDATORY STYLE KEYWORDS (include in every prompt):
- photorealistic, hyperrealistic
- 8k uhd, professional photography
- cinematic lighting, sharp focus
- detailed skin texture, natural skin tones
- DSLR quality, 35mm film, depth of field

NEGATIVE PROMPT (always exclude):
cartoon, anime, illustration, drawing, painting, sketch, 3d render, cgi, artificial, plastic skin

FACE PRESERVATION TECHNIQUES:
- Always start with detailed face description
- Include: eye color, face shape, skin tone, distinctive features
- Specify: "maintaining exact facial features"
- Use: close-up or medium shot for face visibility

Output as JSON:
{
    "prompts": [
        {
            "scene_id": 1,
            "main_prompt": "Photorealistic photograph of [face description], [scene], [lighting], [camera details], photorealistic, hyperrealistic, 8k uhd, professional photography, cinematic lighting",
            "negative_prompt": "cartoon, anime, illustration, drawing, painting, low quality",
            "face_integration": "how face is integrated",
            "lighting_description": "specific lighting setup",
            "camera_details": "camera angle and settings",
            "quality_score_estimate": 0.85
        }
    ],
    "global_settings": {
        "style": "photorealistic",
        "aspect_ratio": "16:9",
        "quality": "ultra"
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
        Создает ФОТОРЕАЛИСТИЧНЫЕ промпты для каждой сцены.
        """
        try:
            scenes = scenes_data.get("scenes", [])

            # Получаем описание лица (КРИТИЧНО для сходства)
            face_description = face_data.get("enhanced_description", {}).get(
                "face_description",
                face_data.get("basic_description", "a person")
            )

            # Ключевые особенности
            key_features = face_data.get("enhanced_description", {}).get(
                "key_features",
                []
            )

            # Название вселенной
            universe_name = universe_data.get("universe_name", "Unknown")

            prompt = f"""Create PHOTOREALISTIC prompts for these scenes from "{universe_name}".

CRITICAL: Even though this may be an animated/cartoon fandom, ALL images must be PHOTOREALISTIC.
Think: "What would this scene look like if it was a real Hollywood movie?"

FACE DESCRIPTION (MUST be preserved in EVERY prompt):
{face_description}

KEY IDENTIFYING FEATURES (MUST include):
{', '.join(key_features) if key_features else 'natural features'}

FANDOM CONTEXT:
Universe: {universe_name}
Original Style: {universe_data.get('style_type', 'mixed')} (BUT we make it PHOTOREALISTIC)

SCENES TO CREATE:
{self._format_scenes(scenes)}

REQUIREMENTS FOR EACH PROMPT:
1. Start with "Photorealistic photograph of a person with [face features]"
2. Transform the animated/cartoon scene into realistic Hollywood-style
3. Include professional cinematic lighting
4. Add camera details (35mm, shallow depth of field, etc.)
5. End with: "photorealistic, hyperrealistic, 8k uhd, professional photography"
6. Negative prompt must include: cartoon, anime, illustration, drawing

Format: 16:9 aspect ratio
"""

            response = self._call_claude([{"role": "user", "content": prompt}])
            prompts_data = self._parse_json_response(response)

            # Гарантируем фотореалистичные настройки
            prompts_data["generation_config"] = {
                "style": "photorealistic",
                "aspect_ratio": "16:9",
                "use_face_swap": True,
                "target_similarity": 0.75,
                "generator": "nano_banana_3_pro"
            }

            # Добавляем обязательные ключевые слова ко всем промптам
            for p in prompts_data.get("prompts", []):
                p["main_prompt"] = self._ensure_photorealistic(p.get("main_prompt", ""))
                p["negative_prompt"] = ", ".join(NEGATIVE_PROMPTS)

            return AgentResult(
                success=True,
                data=prompts_data,
                metadata={
                    "num_prompts": len(prompts_data.get("prompts", [])),
                    "style": "photorealistic",
                    "aspect_ratio": "16:9"
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

    def _ensure_photorealistic(self, prompt: str) -> str:
        """Гарантирует фотореалистичные ключевые слова в промпте"""
        prompt_lower = prompt.lower()

        additions = []

        # Проверяем обязательные ключевые слова
        if "photorealistic" not in prompt_lower:
            additions.append("photorealistic")

        if "8k" not in prompt_lower and "uhd" not in prompt_lower:
            additions.append("8k uhd")

        if "professional photography" not in prompt_lower:
            additions.append("professional photography")

        if "cinematic lighting" not in prompt_lower and "lighting" not in prompt_lower:
            additions.append("cinematic lighting")

        if additions:
            prompt = f"{prompt}, {', '.join(additions)}"

        return prompt

    def enhance_prompt_for_face(self, prompt: str, face_description: str) -> str:
        """
        Улучшает промпт для лучшего сохранения лица.
        """
        if face_description.lower() not in prompt.lower():
            # Вставляем описание лица в начало
            prompt = f"Photorealistic photograph of a person with {face_description}, {prompt}"

        return prompt
