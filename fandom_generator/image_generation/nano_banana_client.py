"""
Nano Banana 3 Pro Client - клиент для генерации изображений
"""
import asyncio
import httpx
from typing import Optional
from dataclasses import dataclass
from pathlib import Path
import base64

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


@dataclass
class GenerationResult:
    """Результат генерации изображения"""
    success: bool
    image: Optional[bytes] = None  # PNG bytes
    image_url: Optional[str] = None
    seed: Optional[int] = None
    generation_time: float = 0.0
    error: Optional[str] = None

    def to_numpy(self) -> Optional["np.ndarray"]:
        """Конвертирует в numpy array (BGR)"""
        if not NUMPY_AVAILABLE or not CV2_AVAILABLE or not self.image:
            return None

        nparr = np.frombuffer(self.image, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    def save(self, path: str):
        """Сохраняет изображение в файл"""
        if self.image:
            with open(path, "wb") as f:
                f.write(self.image)


class NanoBananaClient:
    """
    Клиент для Nano Banana 3 Pro API.
    Генерирует фотореалистичные изображения в формате 16:9.
    """

    # Стандартные настройки для фотореализма
    DEFAULT_SETTINGS = {
        "style": "photorealistic",
        "aspect_ratio": "16:9",
        "resolution": "1920x1080",
        "quality": "ultra",
        "guidance_scale": 7.5,
        "num_inference_steps": 50,
        "negative_prompt": "cartoon, anime, illustration, drawing, painting, sketch, 3d render, cgi, artificial, plastic skin, oversaturated, blurry, low quality"
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: str = "https://api.nanobanana.ai/v1",
        timeout: float = 120.0
    ):
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={
                "Authorization": f"Bearer {api_key}" if api_key else "",
                "Content-Type": "application/json"
            }
        )

    async def generate(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        reference_image: Optional[bytes] = None,
        reference_strength: float = 0.5,
        seed: Optional[int] = None,
        **kwargs
    ) -> GenerationResult:
        """
        Генерирует изображение по промпту.

        Args:
            prompt: Текстовый промпт
            negative_prompt: Негативный промпт (что исключить)
            reference_image: Референсное изображение (для face)
            reference_strength: Сила влияния референса (0-1)
            seed: Seed для воспроизводимости
        """
        try:
            # Формируем запрос
            payload = {
                "prompt": prompt,
                "negative_prompt": negative_prompt or self.DEFAULT_SETTINGS["negative_prompt"],
                "style": self.DEFAULT_SETTINGS["style"],
                "aspect_ratio": self.DEFAULT_SETTINGS["aspect_ratio"],
                "resolution": self.DEFAULT_SETTINGS["resolution"],
                "quality": self.DEFAULT_SETTINGS["quality"],
                "guidance_scale": kwargs.get("guidance_scale", self.DEFAULT_SETTINGS["guidance_scale"]),
                "num_inference_steps": kwargs.get("steps", self.DEFAULT_SETTINGS["num_inference_steps"]),
            }

            if seed is not None:
                payload["seed"] = seed

            # Добавляем референсное изображение если есть
            if reference_image:
                payload["reference_image"] = base64.b64encode(reference_image).decode()
                payload["reference_strength"] = reference_strength

            # Вызываем API
            response = await self.client.post(
                f"{self.api_url}/generate",
                json=payload
            )

            if response.status_code != 200:
                return GenerationResult(
                    success=False,
                    error=f"API error: {response.status_code} - {response.text}"
                )

            data = response.json()

            # Получаем изображение
            if "image_url" in data:
                image_response = await self.client.get(data["image_url"])
                image_bytes = image_response.content
            elif "image_base64" in data:
                image_bytes = base64.b64decode(data["image_base64"])
            else:
                return GenerationResult(
                    success=False,
                    error="No image in response"
                )

            return GenerationResult(
                success=True,
                image=image_bytes,
                image_url=data.get("image_url"),
                seed=data.get("seed"),
                generation_time=data.get("generation_time", 0)
            )

        except httpx.TimeoutException:
            return GenerationResult(
                success=False,
                error="Generation timeout"
            )
        except Exception as e:
            return GenerationResult(
                success=False,
                error=str(e)
            )

    async def generate_with_face(
        self,
        prompt: str,
        face_image_path: str,
        face_strength: float = 0.7,
        **kwargs
    ) -> GenerationResult:
        """
        Генерирует изображение с сохранением лица.

        Args:
            prompt: Промпт с описанием сцены
            face_image_path: Путь к фото лица
            face_strength: Сила сохранения лица (0-1)
        """
        # Загружаем фото
        with open(face_image_path, "rb") as f:
            face_bytes = f.read()

        return await self.generate(
            prompt=prompt,
            reference_image=face_bytes,
            reference_strength=face_strength,
            **kwargs
        )

    async def batch_generate(
        self,
        prompts: list[str],
        face_image_path: Optional[str] = None,
        max_concurrent: int = 3
    ) -> list[GenerationResult]:
        """
        Генерирует несколько изображений параллельно.
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def generate_one(prompt: str) -> GenerationResult:
            async with semaphore:
                if face_image_path:
                    return await self.generate_with_face(prompt, face_image_path)
                return await self.generate(prompt)

        return await asyncio.gather(
            *[generate_one(p) for p in prompts]
        )

    async def close(self):
        """Закрывает клиент"""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


class NanoBananaMockClient(NanoBananaClient):
    """
    Mock клиент для тестирования без реального API.
    """

    async def generate(self, prompt: str, **kwargs) -> GenerationResult:
        """Возвращает placeholder изображение"""
        await asyncio.sleep(0.5)  # Имитация задержки

        # Создаем простое placeholder изображение
        if NUMPY_AVAILABLE and CV2_AVAILABLE:
            # Создаем изображение 16:9
            img = np.zeros((1080, 1920, 3), dtype=np.uint8)
            img[:] = (50, 50, 50)  # Темно-серый фон

            # Добавляем текст
            cv2.putText(
                img,
                "GENERATED IMAGE",
                (600, 500),
                cv2.FONT_HERSHEY_SIMPLEX,
                2,
                (200, 200, 200),
                3
            )
            cv2.putText(
                img,
                prompt[:50] + "..." if len(prompt) > 50 else prompt,
                (100, 600),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (150, 150, 150),
                2
            )

            # Конвертируем в PNG
            _, buffer = cv2.imencode('.png', img)
            image_bytes = buffer.tobytes()
        else:
            # Минимальный PNG placeholder
            image_bytes = b'\x89PNG\r\n\x1a\n...'

        return GenerationResult(
            success=True,
            image=image_bytes,
            seed=12345,
            generation_time=0.5
        )


def get_client(api_key: Optional[str] = None, mock: bool = False) -> NanoBananaClient:
    """
    Получить клиент для генерации.

    Args:
        api_key: API ключ (если None - из env)
        mock: Использовать mock клиент для тестирования
    """
    if mock or not api_key:
        return NanoBananaMockClient()

    return NanoBananaClient(api_key=api_key)
