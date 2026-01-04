"""
Scene Architect Agent - создает 10 культовых сцен из вселенной
Третий агент в пайплайне
"""
from typing import Optional
from dataclasses import dataclass

from .base import BaseAgent, AgentResult


@dataclass
class Scene:
    """Описание сцены"""
    id: int
    title: str
    description: str
    location: str
    mood: str
    lighting: str
    camera_angle: str
    user_role: str  # Какую роль играет пользователь
    other_characters: list[str]
    action: str
    narrative_context: str  # Добро vs зло и т.д.


class SceneArchitectAgent(BaseAgent):
    """
    Агент-архитектор сцен.
    Создает культовые сцены с учетом характеристик пользователя.
    """

    @property
    def name(self) -> str:
        return "Scene Architect"

    @property
    def system_prompt(self) -> str:
        return """You are a master scene designer for creating iconic moments in fictional universes.

Your task is to design 10 epic scenes where the user can be placed within a fandom universe.

CRITICAL RULES:
1. GOOD vs EVIL must be clearly separated - never show hero and villain as friends
2. Each scene must have clear dramatic purpose
3. Scenes should showcase the user in heroic/meaningful roles
4. Consider the visual impact and composition
5. Include variety: action, emotional, epic, intimate moments
6. Match the fandom's visual style and atmosphere

For each scene, consider:
- Dramatic tension and narrative weight
- Optimal camera angle for the user's face visibility
- Lighting that enhances the mood
- Character positioning (user should be prominent)
- Iconic elements from the fandom

Output as JSON:
{
    "scenes": [
        {
            "id": 1,
            "title": "Scene title",
            "description": "Detailed visual description",
            "location": "Specific location in the universe",
            "mood": "epic|dramatic|emotional|action|peaceful|tense",
            "lighting": "Specific lighting description",
            "camera_angle": "close-up|medium shot|wide shot|low angle|high angle|dutch angle",
            "user_role": "What role the user plays",
            "user_position": "center|left|right|foreground",
            "other_characters": ["list of other characters in scene"],
            "action": "What is happening",
            "narrative_context": "good_vs_evil|hero_journey|emotional_moment|etc",
            "key_visual_elements": ["important visual elements"],
            "prompt_notes": "Special notes for prompt creation"
        }
    ],
    "scene_variety": {
        "action_scenes": [1, 5, 8],
        "emotional_scenes": [3, 7],
        "epic_moments": [2, 10],
        "character_scenes": [4, 6, 9]
    }
}"""

    async def run(
        self,
        universe_data: dict,
        face_data: Optional[dict] = None,
        num_scenes: int = 10,
        **kwargs
    ) -> AgentResult:
        """
        Создает сцены для пользователя.

        Args:
            universe_data: Данные о вселенной от Universe Researcher
            face_data: Данные о лице пользователя (для подбора ролей)
            num_scenes: Количество сцен для генерации
        """
        try:
            universe_name = universe_data.get("universe_name", "Unknown")
            key_characters = universe_data.get("key_characters", [])
            locations = universe_data.get("iconic_locations", [])
            style_type = universe_data.get("style_type", "mixed")
            themes = universe_data.get("themes", [])

            # Формируем контекст для Claude
            context = f"""Universe: {universe_name}
Style: {style_type}
Key Characters: {', '.join([c.get('name', '') for c in key_characters[:10]])}
Iconic Locations: {', '.join([l.get('name', '') if isinstance(l, dict) else l for l in locations[:10]])}
Themes: {', '.join(themes)}
"""

            # Добавляем информацию о пользователе если есть
            if face_data:
                user_desc = face_data.get("basic_description", "")
                gender = face_data.get("features", {}).get("estimated_gender", "person")
                age = face_data.get("features", {}).get("estimated_age", "adult")
                context += f"""
User Description: {user_desc}
User appears to be: {gender}, approximately {age} years old
Design scenes that would suit this person's appearance."""

            prompt = f"""{context}

Design {num_scenes} iconic scenes from this universe where the user can be placed.

Remember:
1. Clearly separate good and evil - no friendly hero-villain scenes
2. User should be in heroic/protagonist roles
3. Include variety: action, emotional, epic moments
4. Consider face visibility and good lighting for the user
5. Match the visual style of the fandom"""

            response = self._call_claude([{"role": "user", "content": prompt}])
            scenes_data = self._parse_json_response(response)

            # Валидируем и обогащаем сцены
            scenes = scenes_data.get("scenes", [])
            validated_scenes = []

            for scene in scenes:
                # Проверяем narrative_context
                if scene.get("narrative_context") == "good_vs_evil":
                    # Убеждаемся что пользователь на стороне добра
                    if "villain" in scene.get("user_role", "").lower():
                        scene["user_role"] = scene["user_role"].replace("villain", "hero")

                # Добавляем рекомендации по освещению если нет
                if not scene.get("lighting"):
                    mood = scene.get("mood", "epic")
                    scene["lighting"] = self._get_lighting_for_mood(mood)

                validated_scenes.append(scene)

            scenes_data["scenes"] = validated_scenes
            scenes_data["style_type"] = style_type

            return AgentResult(
                success=True,
                data=scenes_data,
                metadata={
                    "universe": universe_name,
                    "num_scenes": len(validated_scenes)
                }
            )

        except Exception as e:
            return AgentResult(
                success=False,
                data=None,
                error=str(e)
            )

    def _get_lighting_for_mood(self, mood: str) -> str:
        """Возвращает рекомендации по освещению для настроения"""
        lighting_map = {
            "epic": "dramatic golden hour lighting, volumetric rays",
            "dramatic": "high contrast chiaroscuro lighting, deep shadows",
            "emotional": "soft diffused lighting, warm tones",
            "action": "dynamic lighting with motion blur effects",
            "peaceful": "soft natural daylight, gentle shadows",
            "tense": "cold blue lighting, harsh shadows",
            "dark": "low-key lighting, rim light highlighting edges",
            "triumphant": "bright backlighting, lens flare, golden glow"
        }
        return lighting_map.get(mood, "cinematic three-point lighting")
