"""
Configuration for Fandom Generator
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
    """Конфигурация генерации изображений"""
    # Midjourney / Niji
    midjourney_api_url: str = ""
    use_niji: bool = True
    niji_version: str = "6"
    default_ar: str = "16:9"

    # Character reference
    use_cref: bool = True
    cref_weight: int = 80  # --cw параметр (0-100)

    # Style reference
    use_sref: bool = True
    sref_weight: int = 40  # --sw параметр

    # Качество
    quality: str = "1"  # --q параметр
    stylize: int = 100  # --s параметр


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
    midjourney_token: str = field(default_factory=lambda: os.getenv("MIDJOURNEY_TOKEN", ""))
    replicate_api_key: str = field(default_factory=lambda: os.getenv("REPLICATE_API_TOKEN", ""))

    # Подконфигурации
    face: FaceProcessingConfig = field(default_factory=FaceProcessingConfig)
    image: ImageGenerationConfig = field(default_factory=ImageGenerationConfig)
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
