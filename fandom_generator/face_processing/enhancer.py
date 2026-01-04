"""
Face Enhancer - улучшение качества лица после swap
Использует GFPGAN и CodeFormer для реставрации
"""
import numpy as np
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


@dataclass
class EnhanceResult:
    """Результат улучшения лица"""
    image: np.ndarray
    success: bool
    method: str  # gfpgan, codeformer, combined
    message: str = ""


class FaceEnhancer:
    """
    Улучшение качества лица с помощью GFPGAN и CodeFormer.
    Критически важно для финального качества после face swap.
    """

    def __init__(
        self,
        use_gfpgan: bool = True,
        use_codeformer: bool = True,
        gfpgan_model_path: Optional[str] = None,
        codeformer_model_path: Optional[str] = None,
        device: str = "cuda"
    ):
        self.use_gfpgan = use_gfpgan
        self.use_codeformer = use_codeformer
        self.device = device

        self.gfpgan = None
        self.codeformer = None

        if use_gfpgan:
            self._init_gfpgan(gfpgan_model_path)

        if use_codeformer:
            self._init_codeformer(codeformer_model_path)

    def _init_gfpgan(self, model_path: Optional[str] = None):
        """Инициализация GFPGAN"""
        try:
            from gfpgan import GFPGANer

            # Дефолтный путь если не указан
            if model_path is None:
                model_path = "models/GFPGANv1.4.pth"

            self.gfpgan = GFPGANer(
                model_path=model_path,
                upscale=1,  # Не увеличиваем, только улучшаем
                arch='clean',
                channel_multiplier=2,
                bg_upsampler=None
            )
        except ImportError:
            print("GFPGAN не установлен. pip install gfpgan")
            self.use_gfpgan = False
        except Exception as e:
            print(f"Ошибка инициализации GFPGAN: {e}")
            self.use_gfpgan = False

    def _init_codeformer(self, model_path: Optional[str] = None):
        """Инициализация CodeFormer"""
        try:
            # CodeFormer требует специфической установки
            # Заглушка для будущей интеграции
            self.codeformer = None
            self.use_codeformer = False
        except Exception as e:
            print(f"CodeFormer недоступен: {e}")
            self.use_codeformer = False

    def enhance(
        self,
        image: Union[np.ndarray, str, Path],
        method: str = "auto",
        gfpgan_weight: float = 0.7,
        codeformer_fidelity: float = 0.5
    ) -> EnhanceResult:
        """
        Улучшает качество лица на изображении.

        Args:
            image: Входное изображение
            method: Метод улучшения (gfpgan, codeformer, combined, auto)
            gfpgan_weight: Вес GFPGAN (0-1), где 1 = максимальное улучшение
            codeformer_fidelity: Fidelity для CodeFormer (0-1), где 1 = ближе к оригиналу

        Returns:
            EnhanceResult с улучшенным изображением
        """
        # Загрузка изображения
        if isinstance(image, (str, Path)):
            if not CV2_AVAILABLE:
                raise ImportError("OpenCV не установлен")
            img = cv2.imread(str(image))
        else:
            img = image.copy()

        # Определяем метод
        if method == "auto":
            if self.use_gfpgan:
                method = "gfpgan"
            elif self.use_codeformer:
                method = "codeformer"
            else:
                return EnhanceResult(
                    image=img,
                    success=False,
                    method="none",
                    message="Нет доступных методов улучшения"
                )

        # Применяем улучшение
        if method == "gfpgan" and self.gfpgan:
            return self._enhance_gfpgan(img, gfpgan_weight)
        elif method == "codeformer" and self.codeformer:
            return self._enhance_codeformer(img, codeformer_fidelity)
        elif method == "combined":
            return self._enhance_combined(img, gfpgan_weight, codeformer_fidelity)
        else:
            return EnhanceResult(
                image=img,
                success=False,
                method=method,
                message=f"Метод {method} недоступен"
            )

    def _enhance_gfpgan(self, image: np.ndarray, weight: float = 0.7) -> EnhanceResult:
        """Улучшение с помощью GFPGAN"""
        try:
            # GFPGAN работает с BGR
            _, _, restored_img = self.gfpgan.enhance(
                image,
                has_aligned=False,
                only_center_face=False,
                paste_back=True,
                weight=weight
            )

            return EnhanceResult(
                image=restored_img,
                success=True,
                method="gfpgan",
                message=f"GFPGAN улучшение с weight={weight}"
            )
        except Exception as e:
            return EnhanceResult(
                image=image,
                success=False,
                method="gfpgan",
                message=f"Ошибка GFPGAN: {e}"
            )

    def _enhance_codeformer(self, image: np.ndarray, fidelity: float = 0.5) -> EnhanceResult:
        """Улучшение с помощью CodeFormer"""
        # Заглушка - CodeFormer требует отдельной интеграции
        return EnhanceResult(
            image=image,
            success=False,
            method="codeformer",
            message="CodeFormer пока не реализован"
        )

    def _enhance_combined(
        self,
        image: np.ndarray,
        gfpgan_weight: float,
        codeformer_fidelity: float
    ) -> EnhanceResult:
        """Комбинированное улучшение"""
        # Сначала GFPGAN
        if self.use_gfpgan:
            result = self._enhance_gfpgan(image, gfpgan_weight)
            if result.success:
                image = result.image

        # Затем CodeFormer
        if self.use_codeformer:
            result = self._enhance_codeformer(image, codeformer_fidelity)
            if result.success:
                image = result.image

        return EnhanceResult(
            image=image,
            success=True,
            method="combined",
            message="Комбинированное улучшение"
        )


class FaceEnhancerLite:
    """
    Легковесный улучшитель лица без внешних моделей.
    Использует только OpenCV для базовых улучшений.
    """

    @staticmethod
    def enhance(
        image: np.ndarray,
        denoise: bool = True,
        sharpen: bool = True,
        color_correct: bool = True
    ) -> np.ndarray:
        """Базовое улучшение без ML моделей"""
        if not CV2_AVAILABLE:
            return image

        result = image.copy()

        # Денойзинг
        if denoise:
            result = cv2.fastNlMeansDenoisingColored(
                result, None, 5, 5, 7, 21
            )

        # Шарпенинг
        if sharpen:
            kernel = np.array([
                [0, -0.5, 0],
                [-0.5, 3, -0.5],
                [0, -0.5, 0]
            ])
            result = cv2.filter2D(result, -1, kernel)

        # Коррекция цвета (автоуровни)
        if color_correct:
            lab = cv2.cvtColor(result, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            l = clahe.apply(l)
            lab = cv2.merge([l, a, b])
            result = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        return result
