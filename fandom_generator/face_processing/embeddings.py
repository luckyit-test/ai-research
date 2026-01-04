"""
Face Embeddings - извлечение и сравнение эмбеддингов лица
Критически важно для проверки сходства после генерации
"""
import numpy as np
from pathlib import Path
from typing import Optional, Union
from dataclasses import dataclass

try:
    import insightface
    from insightface.app import FaceAnalysis
    INSIGHTFACE_AVAILABLE = True
except ImportError:
    INSIGHTFACE_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


@dataclass
class FaceData:
    """Данные о лице"""
    embedding: np.ndarray  # 512-dim вектор
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    landmarks: np.ndarray  # 5 ключевых точек
    age: Optional[int] = None
    gender: Optional[str] = None
    det_score: float = 0.0  # Уверенность детекции


class FaceEmbeddings:
    """
    Класс для работы с face embeddings через InsightFace.
    Использует модель buffalo_l для максимальной точности.
    """

    def __init__(
        self,
        model_name: str = "buffalo_l",
        det_size: tuple[int, int] = (640, 640),
        det_thresh: float = 0.5,
        providers: Optional[list[str]] = None
    ):
        if not INSIGHTFACE_AVAILABLE:
            raise ImportError(
                "InsightFace не установлен. Установите: pip install insightface onnxruntime-gpu"
            )

        self.det_size = det_size
        self.det_thresh = det_thresh

        # Определяем провайдеры для inference
        if providers is None:
            providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']

        # Инициализация FaceAnalysis
        self.app = FaceAnalysis(
            name=model_name,
            providers=providers
        )
        self.app.prepare(ctx_id=0, det_size=det_size, det_thresh=det_thresh)

    def extract(self, image: Union[np.ndarray, str, Path]) -> Optional[FaceData]:
        """
        Извлекает эмбеддинг из изображения.
        Возвращает данные о лице с наибольшей уверенностью детекции.

        Args:
            image: numpy array (BGR) или путь к файлу

        Returns:
            FaceData или None если лицо не найдено
        """
        if isinstance(image, (str, Path)):
            if not CV2_AVAILABLE:
                raise ImportError("OpenCV не установлен")
            image = cv2.imread(str(image))
            if image is None:
                raise ValueError(f"Не удалось загрузить изображение: {image}")

        # Детекция лиц
        faces = self.app.get(image)

        if not faces:
            return None

        # Берем лицо с наибольшей уверенностью
        best_face = max(faces, key=lambda x: x.det_score)

        return FaceData(
            embedding=best_face.embedding,
            bbox=tuple(best_face.bbox.astype(int)),
            landmarks=best_face.kps,
            age=getattr(best_face, 'age', None),
            gender=getattr(best_face, 'gender', None),
            det_score=float(best_face.det_score)
        )

    def extract_all(self, image: Union[np.ndarray, str, Path]) -> list[FaceData]:
        """Извлекает эмбеддинги всех лиц на изображении"""
        if isinstance(image, (str, Path)):
            if not CV2_AVAILABLE:
                raise ImportError("OpenCV не установлен")
            image = cv2.imread(str(image))

        faces = self.app.get(image)

        return [
            FaceData(
                embedding=face.embedding,
                bbox=tuple(face.bbox.astype(int)),
                landmarks=face.kps,
                age=getattr(face, 'age', None),
                gender=getattr(face, 'gender', None),
                det_score=float(face.det_score)
            )
            for face in faces
        ]

    @staticmethod
    def compute_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
        """
        Вычисляет косинусное сходство между двумя эмбеддингами.

        Returns:
            float: значение от -1 до 1, где >0.5 обычно означает одного человека
        """
        # Нормализация
        emb1_norm = emb1 / np.linalg.norm(emb1)
        emb2_norm = emb2 / np.linalg.norm(emb2)

        # Косинусное сходство
        return float(np.dot(emb1_norm, emb2_norm))

    def verify_similarity(
        self,
        original_image: Union[np.ndarray, str, Path],
        generated_image: Union[np.ndarray, str, Path],
        threshold: float = 0.6
    ) -> tuple[bool, float]:
        """
        Проверяет сходство лица на оригинальном и сгенерированном изображении.

        Args:
            original_image: Оригинальное фото пользователя
            generated_image: Сгенерированное изображение
            threshold: Порог сходства (рекомендуется 0.6-0.7)

        Returns:
            (is_similar, similarity_score)
        """
        original_face = self.extract(original_image)
        generated_face = self.extract(generated_image)

        if original_face is None:
            raise ValueError("Лицо не найдено на оригинальном изображении")
        if generated_face is None:
            return False, 0.0

        similarity = self.compute_similarity(
            original_face.embedding,
            generated_face.embedding
        )

        return similarity >= threshold, similarity


# Вспомогательные функции для быстрого использования
_embeddings_instance: Optional[FaceEmbeddings] = None


def get_embeddings() -> FaceEmbeddings:
    """Получить singleton instance FaceEmbeddings"""
    global _embeddings_instance
    if _embeddings_instance is None:
        _embeddings_instance = FaceEmbeddings()
    return _embeddings_instance


def quick_similarity(img1: Union[np.ndarray, str, Path], img2: Union[np.ndarray, str, Path]) -> float:
    """Быстрая проверка сходства двух изображений"""
    emb = get_embeddings()
    _, score = emb.verify_similarity(img1, img2)
    return score
