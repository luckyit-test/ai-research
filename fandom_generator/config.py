"""
Configuration for Fandom Generator
ВСЕГДА фотореалистичный стиль, формат 16:9
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FaceProcessingConfig:
    """Конфигурация обработки лиц"""
    # Детекция лиц
    det_size: tuple[int, int] = (640, 640)
    det_thresh: float = 0.5

    # Face swap параметры
    similarity_threshold: float = 0.6  # Минимальное сходство для swap

    # Улучшение лица
    use_gfpgan: bool = True
    gfpgan_weight: float = 0.7  # Баланс между улучшением и сохранением
    use_codeformer: bool = True
    codeformer_fidelity: float = 0.5  # Точность к оригиналу (0-1)

    # Blending параметры
    face_mask_blur: int = 10
    face_mask_erode: int = 5

    # Целевые метрики
    target_similarity_score: float = 0.75  # Минимум для принятия


@dataclass
class ImageGenerationConfig:
    """Конфигурация генерации изображений - ВСЕГДА ФОТОРЕАЛИСТИЧНО"""

    # Nano Banana 3 Pro
    generator: str = "nano_banana_3_pro"
    nano_banana_api_url: str = field(default_factory=lambda: os.getenv("NANO_BANANA_API_URL", ""))
    nano_banana_api_key: str = field(default_factory=lambda: os.getenv("NANO_BANANA_API_KEY", ""))

    # ВСЕГДА фотореалистичный стиль
    style: str = "photorealistic"  # Фиксированный стиль

    # ВСЕГДА 16:9
    aspect_ratio: str = "16:9"  # Фиксированный формат

    # Качество
    quality: str = "ultra"  # ultra, high, medium
    resolution: str = "1920x1080"  # Full HD 16:9

    # Фотореалистичные настройки
    photorealism_level: float = 1.0  # Максимальный фотореализм
    lighting_style: str = "cinematic"  # cinematic, natural, studio, dramatic
    camera_style: str = "professional"  # professional, cinematic, portrait


@dataclass
class PromptOptimizationConfig:
    """Конфигурация итеративного улучшения промптов"""
    max_iterations: int = 5  # Максимум итераций улучшения
    min_improvement_threshold: float = 0.05  # Минимальное улучшение для продолжения
    target_score: float = 0.95  # Целевой score промпта

    # Критерии оценки промпта (веса)
    weights: dict = field(default_factory=lambda: {
        "clarity": 0.15,           # Ясность описания
        "photorealism": 0.20,      # Фотореалистичность
        "lighting": 0.15,          # Качество освещения
        "composition": 0.15,       # Композиция кадра
        "face_description": 0.20,  # Описание лица
        "scene_detail": 0.15       # Детализация сцены
    })


@dataclass
class AgentConfig:
    """Конфигурация AI агентов"""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.7

    # Итерации для критика
    max_critic_iterations: int = 3
    min_critic_score: float = 0.9


@dataclass
class Config:
    """Главная конфигурация"""
    # API ключи
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    nano_banana_api_key: str = field(default_factory=lambda: os.getenv("NANO_BANANA_API_KEY", ""))

    # Подконфигурации
    face: FaceProcessingConfig = field(default_factory=FaceProcessingConfig)
    image: ImageGenerationConfig = field(default_factory=ImageGenerationConfig)
    optimization: PromptOptimizationConfig = field(default_factory=PromptOptimizationConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)

    # Пути
    models_dir: str = "./models"
    cache_dir: str = "./cache"
    output_dir: str = "./output"

    @classmethod
    def from_env(cls) -> "Config":
        """Создать конфигурацию из переменных окружения"""
        return cls()


# Глобальная конфигурация
config = Config.from_env()


# Константы стиля - ВСЕГДА ФОТОРЕАЛИСТИЧНО
STYLE_KEYWORDS = [
    "photorealistic",
    "hyperrealistic",
    "8k uhd",
    "professional photography",
    "cinematic lighting",
    "sharp focus",
    "detailed skin texture",
    "natural skin tones",
    "DSLR quality",
    "35mm film",
    "depth of field"
]

# Негативные промпты для фотореализма
NEGATIVE_PROMPTS = [
    "cartoon",
    "anime",
    "illustration",
    "drawing",
    "painting",
    "sketch",
    "3d render",
    "cgi",
    "artificial",
    "plastic skin",
    "oversaturated",
    "blurry",
    "low quality"
]
