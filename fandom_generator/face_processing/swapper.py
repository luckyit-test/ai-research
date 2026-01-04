"""
Face Swapper - замена лица на сгенерированных изображениях
КРИТИЧЕСКИ ВАЖНЫЙ модуль для достижения максимального сходства
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

try:
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False

from .embeddings import FaceEmbeddings, FaceData


@dataclass
class SwapResult:
    """Результат face swap"""
    image: np.ndarray  # Результирующее изображение
    success: bool
    similarity_before: float  # Сходство до swap
    similarity_after: float  # Сходство после swap
    message: str = ""


class FaceSwapper:
    """
    Face Swap с использованием InsightFace inswapper.
    Оптимизирован для максимального сходства.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        det_size: tuple[int, int] = (640, 640),
        providers: Optional[list[str]] = None
    ):
        """
        Args:
            model_path: Путь к модели inswapper_128.onnx
            det_size: Размер для детекции лиц
            providers: ONNX провайдеры (GPU/CPU)
        """
        if not INSIGHTFACE_AVAILABLE:
            raise ImportError("InsightFace не установлен")
        if not CV2_AVAILABLE:
            raise ImportError("OpenCV не установлен")

        self.det_size = det_size

        if providers is None:
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']

        # Face analyzer для детекции
        self.face_analyzer = FaceAnalysis(
            name='buffalo_l',
            providers=providers
        )
        self.face_analyzer.prepare(ctx_id=0, det_size=det_size)

        # Загрузка swapper модели
        self.swapper = None
        if model_path:
            self._load_swapper(model_path, providers)

        # Embeddings для проверки сходства
        self.embeddings = FaceEmbeddings(det_size=det_size)

    def _load_swapper(self, model_path: str, providers: list[str]):
        """Загружает модель inswapper"""
        import onnxruntime

        self.swapper = insightface.model_zoo.get_model(
            model_path,
            providers=providers
        )

    def swap(
        self,
        source_image: Union[np.ndarray, str, Path],
        target_image: Union[np.ndarray, str, Path],
        source_face_index: int = 0,
        target_face_index: int = 0,
        blend_ratio: float = 1.0
    ) -> SwapResult:
        """
        Выполняет face swap.

        Args:
            source_image: Изображение-источник (лицо пользователя)
            target_image: Целевое изображение (сгенерированное)
            source_face_index: Индекс лица на source (если несколько)
            target_face_index: Индекс лица на target (если несколько)
            blend_ratio: Сила смешивания (0-1)

        Returns:
            SwapResult с результатом
        """
        # Загрузка изображений
        if isinstance(source_image, (str, Path)):
            source_img = cv2.imread(str(source_image))
        else:
            source_img = source_image.copy()

        if isinstance(target_image, (str, Path)):
            target_img = cv2.imread(str(target_image))
        else:
            target_img = target_image.copy()

        # Детекция лиц
        source_faces = self.face_analyzer.get(source_img)
        target_faces = self.face_analyzer.get(target_img)

        if not source_faces:
            return SwapResult(
                image=target_img,
                success=False,
                similarity_before=0,
                similarity_after=0,
                message="Лицо не найдено на исходном изображении"
            )

        if not target_faces:
            return SwapResult(
                image=target_img,
                success=False,
                similarity_before=0,
                similarity_after=0,
                message="Лицо не найдено на целевом изображении"
            )

        # Выбираем нужные лица
        source_face = sorted(source_faces, key=lambda x: x.det_score, reverse=True)[source_face_index]
        target_face = sorted(target_faces, key=lambda x: x.det_score, reverse=True)[target_face_index]

        # Сходство до swap
        similarity_before = FaceEmbeddings.compute_similarity(
            source_face.embedding,
            target_face.embedding
        )

        # Выполняем swap
        if self.swapper is None:
            return SwapResult(
                image=target_img,
                success=False,
                similarity_before=similarity_before,
                similarity_after=similarity_before,
                message="Swapper модель не загружена"
            )

        result_img = self.swapper.get(
            target_img,
            target_face,
            source_face,
            paste_back=True
        )

        # Blending для более естественного результата
        if blend_ratio < 1.0:
            result_img = cv2.addWeighted(
                result_img, blend_ratio,
                target_img, 1 - blend_ratio,
                0
            )

        # Проверяем сходство после swap
        result_faces = self.face_analyzer.get(result_img)
        if result_faces:
            result_face = sorted(result_faces, key=lambda x: x.det_score, reverse=True)[0]
            similarity_after = FaceEmbeddings.compute_similarity(
                source_face.embedding,
                result_face.embedding
            )
        else:
            similarity_after = 0

        return SwapResult(
            image=result_img,
            success=True,
            similarity_before=similarity_before,
            similarity_after=similarity_after,
            message=f"Сходство улучшено: {similarity_before:.2f} -> {similarity_after:.2f}"
        )

    def swap_with_mask_refinement(
        self,
        source_image: Union[np.ndarray, str, Path],
        target_image: Union[np.ndarray, str, Path],
        mask_blur: int = 10,
        mask_erode: int = 5
    ) -> SwapResult:
        """
        Face swap с улучшенной маской для более естественного результата.
        Рекомендуется для фотореалистичных изображений.
        """
        # Базовый swap
        result = self.swap(source_image, target_image)

        if not result.success:
            return result

        # Загружаем target для создания маски
        if isinstance(target_image, (str, Path)):
            target_img = cv2.imread(str(target_image))
        else:
            target_img = target_image.copy()

        # Получаем область лица для маски
        target_faces = self.face_analyzer.get(target_img)
        if not target_faces:
            return result

        target_face = sorted(target_faces, key=lambda x: x.det_score, reverse=True)[0]

        # Создаем маску на основе landmarks
        mask = self._create_face_mask(
            target_img.shape[:2],
            target_face,
            blur=mask_blur,
            erode=mask_erode
        )

        # Применяем маску для плавного перехода
        mask_3ch = np.stack([mask] * 3, axis=-1)
        blended = (result.image * mask_3ch + target_img * (1 - mask_3ch)).astype(np.uint8)

        return SwapResult(
            image=blended,
            success=True,
            similarity_before=result.similarity_before,
            similarity_after=result.similarity_after,
            message=result.message + " (с улучшенной маской)"
        )

    def _create_face_mask(
        self,
        shape: tuple[int, int],
        face,
        blur: int = 10,
        erode: int = 5
    ) -> np.ndarray:
        """Создает маску для области лица"""
        h, w = shape
        mask = np.zeros((h, w), dtype=np.float32)

        # Используем landmarks для создания полигона лица
        landmarks = face.kps.astype(np.int32)

        # Создаем выпуклую оболочку вокруг landmarks
        hull = cv2.convexHull(landmarks)
        cv2.fillConvexPoly(mask, hull, 1.0)

        # Расширяем маску до bbox
        x1, y1, x2, y2 = face.bbox.astype(int)
        cv2.rectangle(mask, (x1, y1), (x2, y2), 1.0, -1)

        # Эрозия для уменьшения маски
        if erode > 0:
            kernel = np.ones((erode, erode), np.uint8)
            mask = cv2.erode(mask, kernel, iterations=1)

        # Размытие для плавного перехода
        if blur > 0:
            mask = cv2.GaussianBlur(mask, (blur * 2 + 1, blur * 2 + 1), 0)

        return mask

    def iterative_swap(
        self,
        source_image: Union[np.ndarray, str, Path],
        target_image: Union[np.ndarray, str, Path],
        target_similarity: float = 0.75,
        max_iterations: int = 3
    ) -> SwapResult:
        """
        Итеративный face swap до достижения целевого сходства.
        Полезно когда один проход не дает нужного результата.
        """
        current_target = target_image
        best_result = None
        best_similarity = 0

        for i in range(max_iterations):
            result = self.swap_with_mask_refinement(source_image, current_target)

            if not result.success:
                break

            if result.similarity_after > best_similarity:
                best_result = result
                best_similarity = result.similarity_after

            if result.similarity_after >= target_similarity:
                result.message = f"Целевое сходство достигнуто за {i+1} итераций"
                return result

            # Используем результат как новый target
            current_target = result.image

        if best_result:
            best_result.message = f"Лучшее сходство после {max_iterations} итераций: {best_similarity:.2f}"
            return best_result

        return SwapResult(
            image=target_image if isinstance(target_image, np.ndarray) else cv2.imread(str(target_image)),
            success=False,
            similarity_before=0,
            similarity_after=0,
            message="Не удалось достичь целевого сходства"
        )
