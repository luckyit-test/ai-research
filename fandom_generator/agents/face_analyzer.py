"""
Face Analyzer Agent - анализирует фото пользователя
Первый агент в пайплайне
"""
from typing import Optional, Union
from pathlib import Path
import numpy as np

from .base import BaseAgent, AgentResult
from ..face_processing import FaceAnalyzer, FaceEmbeddings
from ..face_processing.analyzer import FaceFeatures


class FaceAnalyzerAgent(BaseAgent):
    """
    Агент анализа лица.
    Извлекает характеристики лица для использования в промптах.
    """

    @property
    def name(self) -> str:
        return "Face Analyzer"

    @property
    def system_prompt(self) -> str:
        return """You are an expert at analyzing human faces and describing them for AI image generation.

Your task is to create detailed, accurate descriptions of facial features that will help maintain
identity consistency when generating images of this person in different styles and settings.

Focus on:
1. Distinctive features that make this person unique
2. Face shape and proportions
3. Eye characteristics (color, shape, size)
4. Hair style and color
5. Skin tone and any notable features
6. Age range and gender presentation

Output your analysis as JSON with the following structure:
{
    "face_description": "detailed textual description for prompts",
    "key_features": ["list", "of", "distinctive", "features"],
    "style_recommendations": {
        "anime": "how to adapt for anime style",
        "photorealistic": "how to maintain in photorealistic",
        "cinematic": "recommendations for cinematic look"
    },
    "prompt_keywords": ["important", "keywords", "for", "prompts"]
}"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._face_analyzer = None
        self._embeddings = None

    @property
    def face_analyzer(self) -> FaceAnalyzer:
        if self._face_analyzer is None:
            self._face_analyzer = FaceAnalyzer()
        return self._face_analyzer

    @property
    def embeddings(self) -> FaceEmbeddings:
        if self._embeddings is None:
            self._embeddings = FaceEmbeddings()
        return self._embeddings

    async def run(
        self,
        image_path: Union[str, Path],
        enhance_with_ai: bool = True,
        **kwargs
    ) -> AgentResult:
        """
        Анализирует лицо на изображении.

        Args:
            image_path: Путь к изображению пользователя
            enhance_with_ai: Использовать Claude для улучшения описания
        """
        try:
            # Извлекаем эмбеддинг для последующей проверки сходства
            face_data = self.embeddings.extract(str(image_path))
            if face_data is None:
                return AgentResult(
                    success=False,
                    data=None,
                    error="Лицо не найдено на изображении"
                )

            # Анализируем черты лица
            features = self.face_analyzer.analyze(str(image_path))

            # Получаем оптимальные углы
            angles = self.face_analyzer.get_optimal_angles(str(image_path))

            # Базовое описание
            basic_description = features.to_prompt_description()

            result_data = {
                "face_embedding": face_data.embedding.tolist(),
                "basic_description": basic_description,
                "features": {
                    "face_shape": features.face_shape,
                    "skin_tone": features.skin_tone,
                    "eye_color": features.eye_color,
                    "eye_shape": features.eye_shape,
                    "hair_color": features.hair_color,
                    "hair_style": features.hair_style,
                    "estimated_age": features.estimated_age,
                    "estimated_gender": features.estimated_gender,
                    "distinctive_features": features.distinctive_features,
                },
                "optimal_angles": angles,
                "det_score": face_data.det_score
            }

            # Улучшаем описание с помощью AI
            if enhance_with_ai and self.client:
                enhanced = await self._enhance_description(features, basic_description)
                result_data["enhanced_description"] = enhanced

            return AgentResult(
                success=True,
                data=result_data,
                metadata={"image_path": str(image_path)}
            )

        except Exception as e:
            return AgentResult(
                success=False,
                data=None,
                error=str(e)
            )

    async def _enhance_description(
        self,
        features: FaceFeatures,
        basic_description: str
    ) -> dict:
        """Улучшает описание с помощью Claude"""
        prompt = f"""Based on this basic face analysis, create an enhanced description for AI image generation:

Basic description: {basic_description}

Face shape: {features.face_shape}
Skin tone: {features.skin_tone}
Eye color: {features.eye_color}
Hair: {features.hair_color} {features.hair_style}
Estimated age: {features.estimated_age}
Gender: {features.estimated_gender}

Create a JSON response with enhanced descriptions for different styles."""

        response = self._call_claude([{"role": "user", "content": prompt}])
        return self._parse_json_response(response)
