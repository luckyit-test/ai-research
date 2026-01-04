"""
Universe Researcher Agent - исследует вселенную фандома
Второй агент в пайплайне
"""
from typing import Optional
from dataclasses import dataclass, field

from .base import BaseAgent, AgentResult


@dataclass
class UniverseData:
    """Данные о вселенной фандома"""
    name: str
    style_type: str  # anime, live_action, animated, comic, game
    description: str
    visual_style: str
    color_palette: list[str]
    key_characters: list[dict]
    iconic_locations: list[str]
    themes: list[str]
    era_setting: str  # medieval, modern, futuristic, fantasy
    mood: str  # dark, light, epic, comedic


class UniverseResearcherAgent(BaseAgent):
    """
    Агент исследования вселенной.
    Собирает информацию о фандоме для создания аутентичных сцен.
    """

    @property
    def name(self) -> str:
        return "Universe Researcher"

    @property
    def system_prompt(self) -> str:
        return """You are an expert researcher of fictional universes, fandoms, and media properties.

Your task is to analyze a given fandom and provide comprehensive information about:
1. Visual style (anime, live-action, CGI, hand-drawn, etc.)
2. Color palette and lighting characteristics
3. Key characters with their visual descriptions
4. Iconic locations and settings
5. Core themes and narrative elements
6. Era/setting (medieval, modern, futuristic, etc.)
7. Overall mood and atmosphere

This information will be used to generate authentic fan art that matches the original style.

IMPORTANT: Differentiate between:
- ANIME/ANIMATED fandoms (Dragon Ball, Naruto, One Piece, etc.) - use anime/stylized prompts
- LIVE-ACTION fandoms (Harry Potter, Marvel MCU, Star Wars) - use photorealistic prompts
- GAME fandoms - match the game's visual style
- COMIC fandoms - match the comic art style

Output your research as JSON:
{
    "universe_name": "Name of the fandom",
    "style_type": "anime|live_action|animated|comic|game|mixed",
    "description": "Brief description of the universe",
    "visual_style": {
        "primary_style": "main visual approach",
        "rendering": "2D|3D|photorealistic|stylized",
        "line_work": "description of line style if applicable",
        "color_approach": "vibrant|muted|realistic|etc"
    },
    "color_palette": ["#hex1", "#hex2", ...],
    "lighting_style": "description of typical lighting",
    "key_characters": [
        {
            "name": "Character name",
            "role": "protagonist|antagonist|supporting",
            "visual_description": "detailed visual description",
            "signature_elements": ["iconic items/features"]
        }
    ],
    "iconic_locations": [
        {
            "name": "Location name",
            "description": "visual description",
            "mood": "mood/atmosphere"
        }
    ],
    "themes": ["core themes"],
    "era_setting": "time period/setting type",
    "mood": "overall mood",
    "prompt_style_guide": {
        "midjourney_params": "--style raw --s 100 etc",
        "niji_params": "--niji 6 --style etc",
        "style_keywords": ["important style keywords"],
        "avoid_keywords": ["things to avoid"]
    }
}"""

    # Кэш для известных фандомов
    KNOWN_FANDOMS = {
        "dragon ball": {
            "style_type": "anime",
            "niji_recommended": True,
            "style_keywords": ["shonen anime", "dynamic action", "ki aura", "power-up transformation"]
        },
        "harry potter": {
            "style_type": "live_action",
            "niji_recommended": False,
            "style_keywords": ["magical realism", "British aesthetic", "gothic architecture", "warm lighting"]
        },
        "naruto": {
            "style_type": "anime",
            "niji_recommended": True,
            "style_keywords": ["ninja", "chakra effects", "dynamic poses", "Japanese aesthetic"]
        },
        "marvel": {
            "style_type": "live_action",
            "niji_recommended": False,
            "style_keywords": ["superhero", "cinematic", "dramatic lighting", "action poses"]
        },
        "one piece": {
            "style_type": "anime",
            "niji_recommended": True,
            "style_keywords": ["pirate adventure", "exaggerated proportions", "vibrant colors"]
        },
        "star wars": {
            "style_type": "live_action",
            "niji_recommended": False,
            "style_keywords": ["space opera", "cinematic", "practical effects aesthetic", "lightsaber glow"]
        },
        "demon slayer": {
            "style_type": "anime",
            "niji_recommended": True,
            "style_keywords": ["ufotable style", "breathing techniques", "dynamic water/fire effects"]
        },
        "game of thrones": {
            "style_type": "live_action",
            "niji_recommended": False,
            "style_keywords": ["medieval fantasy", "gritty realism", "dark atmosphere", "political drama"]
        }
    }

    async def run(
        self,
        fandom_name: str,
        use_cache: bool = True,
        **kwargs
    ) -> AgentResult:
        """
        Исследует вселенную фандома.

        Args:
            fandom_name: Название фандома
            use_cache: Использовать кэш для известных фандомов
        """
        try:
            fandom_lower = fandom_name.lower()

            # Проверяем известные фандомы для быстрого определения стиля
            known_data = None
            for known_name, data in self.KNOWN_FANDOMS.items():
                if known_name in fandom_lower:
                    known_data = data
                    break

            # Запрашиваем полное исследование через Claude
            prompt = f"""Research the fictional universe/fandom: "{fandom_name}"

Provide comprehensive information about this universe for creating authentic fan art.
Focus on visual style, key characters, iconic scenes, and atmosphere.

{"Note: This appears to be an ANIME fandom, optimize for Niji mode." if known_data and known_data.get("niji_recommended") else ""}
{"Note: This appears to be a LIVE-ACTION fandom, optimize for photorealistic generation." if known_data and known_data.get("style_type") == "live_action" else ""}
"""

            response = self._call_claude([{"role": "user", "content": prompt}])
            universe_data = self._parse_json_response(response)

            # Добавляем данные из кэша если есть
            if known_data:
                universe_data["known_fandom_hints"] = known_data

            # Определяем рекомендуемый режим генерации
            style_type = universe_data.get("style_type", "unknown")
            universe_data["generation_mode"] = {
                "use_niji": style_type in ["anime", "animated"],
                "use_cref": True,  # Character reference всегда полезен
                "photorealistic": style_type == "live_action",
                "stylize_level": 100 if style_type == "live_action" else 250
            }

            return AgentResult(
                success=True,
                data=universe_data,
                metadata={"fandom_name": fandom_name}
            )

        except Exception as e:
            return AgentResult(
                success=False,
                data=None,
                error=str(e)
            )

    def get_style_recommendations(self, universe_data: dict) -> dict:
        """Возвращает рекомендации по стилю для генерации"""
        style_type = universe_data.get("style_type", "mixed")

        if style_type == "anime":
            return {
                "mode": "niji",
                "params": "--niji 6 --style expressive",
                "cref_weight": 80,
                "sref_weight": 50,
                "aspect_ratio": "16:9"
            }
        elif style_type == "live_action":
            return {
                "mode": "midjourney",
                "params": "--style raw --s 50",
                "cref_weight": 100,
                "sref_weight": 30,
                "aspect_ratio": "16:9"
            }
        else:
            return {
                "mode": "midjourney",
                "params": "--s 100",
                "cref_weight": 90,
                "sref_weight": 40,
                "aspect_ratio": "16:9"
            }
