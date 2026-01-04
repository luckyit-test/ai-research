"""
Image Generator Agent - генерирует изображения и применяет face swap
Финальный агент в пайплайне
"""
from typing import Optional, Union
from pathlib import Path
from dataclasses import dataclass
import numpy as np
import asyncio

from .base import BaseAgent, AgentResult

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


@dataclass
class GeneratedImage:
    """Сгенерированное изображение"""
    scene_id: int
    image: np.ndarray
    prompt_used: str
    similarity_score: float
    generation_params: dict
    face_swap_applied: bool


class ImageGeneratorAgent(BaseAgent):
    """
    Агент генерации изображений.
    Оркестрирует генерацию через Midjourney/Niji и применяет face swap.
    """

    @property
    def name(self) -> str:
        return "Image Generator"

    @property
    def system_prompt(self) -> str:
        return "Image generation agent - executes prompts and manages face swap pipeline"

    def __init__(
        self,
        midjourney_client=None,
        face_swapper=None,
        face_enhancer=None,
        embeddings=None,
        target_similarity: float = 0.75,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.midjourney_client = midjourney_client
        self.face_swapper = face_swapper
        self.face_enhancer = face_enhancer
        self.embeddings = embeddings
        self.target_similarity = target_similarity

    async def run(
        self,
        final_prompts: list[dict],
        user_image_path: str,
        face_embedding: list[float],
        generation_config: dict,
        **kwargs
    ) -> AgentResult:
        """
        Генерирует изображения для всех промптов.

        Args:
            final_prompts: Финальные промпты от Prompt Critic
            user_image_path: Путь к фото пользователя
            face_embedding: Эмбеддинг лица пользователя
            generation_config: Конфигурация генерации
        """
        try:
            results = []
            user_embedding = np.array(face_embedding)

            for prompt_data in final_prompts:
                scene_id = prompt_data.get("scene_id", 0)
                prompt = prompt_data.get("main_prompt", "")
                params = prompt_data.get("technical_params", {})

                # Определяем режим генерации
                use_niji = generation_config.get("use_niji", False)
                mode_params = params.get("niji" if use_niji else "midjourney", "")

                # Генерируем базовое изображение
                generated_image = await self._generate_base_image(
                    prompt=prompt,
                    params=mode_params,
                    user_image_url=user_image_path  # Для --cref
                )

                if generated_image is None:
                    results.append({
                        "scene_id": scene_id,
                        "success": False,
                        "error": "Failed to generate base image"
                    })
                    continue

                # Проверяем сходство
                initial_similarity = await self._check_similarity(
                    generated_image, user_embedding
                )

                final_image = generated_image
                face_swap_applied = False

                # Применяем face swap если сходство недостаточное
                if initial_similarity < self.target_similarity:
                    if self.face_swapper:
                        swap_result = await self._apply_face_swap(
                            source_image=user_image_path,
                            target_image=generated_image
                        )

                        if swap_result["success"]:
                            final_image = swap_result["image"]
                            face_swap_applied = True

                # Улучшаем лицо
                if self.face_enhancer and face_swap_applied:
                    enhanced = await self._enhance_face(final_image)
                    if enhanced is not None:
                        final_image = enhanced

                # Финальная проверка сходства
                final_similarity = await self._check_similarity(
                    final_image, user_embedding
                )

                results.append({
                    "scene_id": scene_id,
                    "success": True,
                    "image": final_image,
                    "prompt": prompt,
                    "initial_similarity": initial_similarity,
                    "final_similarity": final_similarity,
                    "face_swap_applied": face_swap_applied,
                    "meets_threshold": final_similarity >= self.target_similarity
                })

            # Статистика
            successful = [r for r in results if r.get("success")]
            avg_similarity = sum(r.get("final_similarity", 0) for r in successful) / len(successful) if successful else 0
            meets_threshold_count = sum(1 for r in successful if r.get("meets_threshold"))

            return AgentResult(
                success=True,
                data={
                    "generated_images": results,
                    "statistics": {
                        "total_scenes": len(final_prompts),
                        "successful": len(successful),
                        "failed": len(final_prompts) - len(successful),
                        "average_similarity": avg_similarity,
                        "meets_threshold": meets_threshold_count,
                        "face_swap_applied_count": sum(1 for r in successful if r.get("face_swap_applied"))
                    }
                },
                metadata={"target_similarity": self.target_similarity}
            )

        except Exception as e:
            return AgentResult(
                success=False,
                data=None,
                error=str(e)
            )

    async def _generate_base_image(
        self,
        prompt: str,
        params: str,
        user_image_url: Optional[str] = None
    ) -> Optional[np.ndarray]:
        """Генерирует базовое изображение через Midjourney/Niji API"""
        if self.midjourney_client is None:
            # Заглушка для тестирования
            return self._create_placeholder_image()

        # Формируем полный промпт с параметрами
        full_prompt = prompt
        if user_image_url and "--cref" in params:
            # Вставляем URL в --cref
            params = params.replace("--cref URL", f"--cref {user_image_url}")

        full_prompt = f"{prompt} {params}".strip()

        try:
            # Вызов API (интерфейс зависит от используемого клиента)
            result = await self.midjourney_client.imagine(full_prompt)
            return result.image if result else None
        except Exception as e:
            print(f"Generation error: {e}")
            return None

    async def _check_similarity(
        self,
        image: np.ndarray,
        user_embedding: np.ndarray
    ) -> float:
        """Проверяет сходство лица на изображении с оригиналом"""
        if self.embeddings is None:
            return 0.5  # Нет проверки - возвращаем среднее

        try:
            face_data = self.embeddings.extract(image)
            if face_data is None:
                return 0.0

            from ..face_processing.embeddings import FaceEmbeddings
            similarity = FaceEmbeddings.compute_similarity(
                user_embedding,
                face_data.embedding
            )
            return similarity
        except Exception:
            return 0.0

    async def _apply_face_swap(
        self,
        source_image: Union[str, np.ndarray],
        target_image: np.ndarray
    ) -> dict:
        """Применяет face swap"""
        if self.face_swapper is None:
            return {"success": False, "error": "Face swapper not initialized"}

        try:
            result = self.face_swapper.iterative_swap(
                source_image=source_image,
                target_image=target_image,
                target_similarity=self.target_similarity
            )
            return {
                "success": result.success,
                "image": result.image,
                "similarity": result.similarity_after
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _enhance_face(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Улучшает качество лица"""
        if self.face_enhancer is None:
            return image

        try:
            result = self.face_enhancer.enhance(image)
            return result.image if result.success else image
        except Exception:
            return image

    def _create_placeholder_image(self, size: tuple = (1024, 576)) -> np.ndarray:
        """Создает заглушку изображения для тестирования"""
        if CV2_AVAILABLE:
            return np.zeros((size[1], size[0], 3), dtype=np.uint8)
        return np.zeros((size[1], size[0], 3), dtype=np.uint8)


class MidjourneyClientMock:
    """
    Mock клиент Midjourney для тестирования.
    Замените на реальную интеграцию.
    """

    @dataclass
    class ImagineResult:
        image: np.ndarray
        url: str
        job_id: str

    async def imagine(self, prompt: str) -> Optional["MidjourneyClientMock.ImagineResult"]:
        """Имитирует генерацию изображения"""
        # В реальности здесь будет вызов Midjourney API
        await asyncio.sleep(0.1)  # Имитация задержки

        placeholder = np.random.randint(0, 255, (576, 1024, 3), dtype=np.uint8)

        return self.ImagineResult(
            image=placeholder,
            url="https://placeholder.url/image.png",
            job_id="mock-job-id"
        )
