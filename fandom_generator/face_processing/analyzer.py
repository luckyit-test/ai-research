"""
Face Analyzer - анализ черт лица для создания точных текстовых описаний
Критически важно для промпт-инженерии
"""
from dataclasses import dataclass, field
from typing import Optional, Union
from pathlib import Path
import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

from .embeddings import FaceEmbeddings, FaceData


@dataclass
class FaceFeatures:
    """Детальное описание черт лица"""
    # Основные характеристики
    face_shape: str = ""  # oval, round, square, heart, oblong
    skin_tone: str = ""  # fair, light, medium, olive, tan, brown, dark

    # Глаза
    eye_color: str = ""  # blue, green, brown, hazel, gray, amber
    eye_shape: str = ""  # almond, round, hooded, monolid, upturned, downturned
    eye_size: str = ""  # small, medium, large

    # Брови
    eyebrow_shape: str = ""  # arched, straight, curved, s-shaped
    eyebrow_thickness: str = ""  # thin, medium, thick

    # Нос
    nose_shape: str = ""  # straight, roman, button, snub, hawk
    nose_size: str = ""  # small, medium, large

    # Губы
    lip_shape: str = ""  # full, thin, heart, wide
    lip_size: str = ""  # small, medium, full

    # Волосы
    hair_color: str = ""  # black, brown, blonde, red, gray, white
    hair_style: str = ""  # short, medium, long, curly, straight, wavy
    hair_texture: str = ""  # straight, wavy, curly, coily

    # Особенности
    facial_hair: str = ""  # none, stubble, beard, mustache, goatee
    distinctive_features: list[str] = field(default_factory=list)  # freckles, dimples, moles, scars

    # Возраст и пол (приблизительно)
    estimated_age: Optional[int] = None
    estimated_gender: Optional[str] = None

    def to_prompt_description(self, style: str = "photorealistic") -> str:
        """
        Генерирует текстовое описание для промпта.

        Args:
            style: Стиль описания (photorealistic, anime, artistic)
        """
        parts = []

        # Основа
        if self.estimated_gender:
            parts.append(f"a {self.estimated_gender}")
        else:
            parts.append("a person")

        # Возраст
        if self.estimated_age:
            if self.estimated_age < 18:
                parts.append("young")
            elif self.estimated_age < 30:
                parts.append("in their twenties")
            elif self.estimated_age < 40:
                parts.append("in their thirties")
            elif self.estimated_age < 50:
                parts.append("middle-aged")
            else:
                parts.append("mature")

        # Форма лица и тон кожи
        if self.skin_tone:
            parts.append(f"with {self.skin_tone} skin")
        if self.face_shape:
            parts.append(f"and {self.face_shape} face shape")

        # Глаза (важно для сходства!)
        eye_desc = []
        if self.eye_color:
            eye_desc.append(self.eye_color)
        if self.eye_shape:
            eye_desc.append(self.eye_shape)
        if eye_desc:
            parts.append(f"{' '.join(eye_desc)} eyes")

        # Волосы
        hair_desc = []
        if self.hair_color:
            hair_desc.append(self.hair_color)
        if self.hair_texture:
            hair_desc.append(self.hair_texture)
        if self.hair_style:
            hair_desc.append(self.hair_style)
        if hair_desc:
            parts.append(f"{' '.join(hair_desc)} hair")

        # Особенности (критично для узнаваемости!)
        if self.distinctive_features:
            parts.append(f"with {', '.join(self.distinctive_features)}")

        # Растительность на лице
        if self.facial_hair and self.facial_hair != "none":
            parts.append(f"with {self.facial_hair}")

        return ", ".join(parts)


class FaceAnalyzer:
    """
    Анализатор черт лица.
    Комбинирует компьютерное зрение с AI для создания точных описаний.
    """

    def __init__(self, embeddings: Optional[FaceEmbeddings] = None):
        self.embeddings = embeddings or FaceEmbeddings()

    def analyze(
        self,
        image: Union[np.ndarray, str, Path],
        use_ai_enhancement: bool = True
    ) -> FaceFeatures:
        """
        Анализирует лицо и возвращает детальное описание черт.

        Args:
            image: Изображение для анализа
            use_ai_enhancement: Использовать AI для улучшения описания
        """
        # Загружаем изображение
        if isinstance(image, (str, Path)):
            if not CV2_AVAILABLE:
                raise ImportError("OpenCV не установлен")
            img = cv2.imread(str(image))
        else:
            img = image

        # Получаем базовые данные через InsightFace
        face_data = self.embeddings.extract(img)
        if face_data is None:
            raise ValueError("Лицо не найдено на изображении")

        features = FaceFeatures(
            estimated_age=face_data.age,
            estimated_gender="female" if face_data.gender == 0 else "male" if face_data.gender == 1 else None
        )

        # Анализ на основе изображения
        features = self._analyze_visual_features(img, face_data, features)

        return features

    def _analyze_visual_features(
        self,
        image: np.ndarray,
        face_data: FaceData,
        features: FaceFeatures
    ) -> FaceFeatures:
        """Анализирует визуальные характеристики лица"""
        if not CV2_AVAILABLE:
            return features

        # Вырезаем область лица
        x1, y1, x2, y2 = face_data.bbox
        face_crop = image[y1:y2, x1:x2]

        if face_crop.size == 0:
            return features

        # Анализ тона кожи
        features.skin_tone = self._analyze_skin_tone(face_crop)

        # Анализ формы лица по соотношению сторон
        h, w = face_crop.shape[:2]
        ratio = w / h if h > 0 else 1

        if ratio > 0.9:
            features.face_shape = "round"
        elif ratio > 0.8:
            features.face_shape = "oval"
        elif ratio > 0.7:
            features.face_shape = "heart"
        else:
            features.face_shape = "oblong"

        return features

    def _analyze_skin_tone(self, face_crop: np.ndarray) -> str:
        """Определяет тон кожи по изображению"""
        # Конвертируем в LAB для лучшего анализа цвета кожи
        lab = cv2.cvtColor(face_crop, cv2.COLOR_BGR2LAB)

        # Берем центральную область (там обычно лоб/щеки)
        h, w = lab.shape[:2]
        center = lab[h//4:3*h//4, w//4:3*w//4]

        # Средняя яркость (L канал)
        l_mean = np.mean(center[:, :, 0])

        if l_mean > 200:
            return "fair"
        elif l_mean > 170:
            return "light"
        elif l_mean > 140:
            return "medium"
        elif l_mean > 110:
            return "olive"
        elif l_mean > 80:
            return "tan"
        elif l_mean > 50:
            return "brown"
        else:
            return "dark"

    def get_optimal_angles(self, image: Union[np.ndarray, str, Path]) -> dict:
        """
        Определяет оптимальные углы камеры для данного лица.
        Полезно для генерации более похожих изображений.
        """
        face_data = self.embeddings.extract(image)
        if face_data is None:
            return {"angle": "front", "tilt": "neutral"}

        # Анализ landmarks для определения ракурса
        landmarks = face_data.landmarks

        # Расстояние между глазами (для определения поворота)
        left_eye = landmarks[0]
        right_eye = landmarks[1]
        eye_distance = np.linalg.norm(left_eye - right_eye)

        # Анализ симметрии
        nose = landmarks[2]
        center_x = (left_eye[0] + right_eye[0]) / 2

        face_turn = (nose[0] - center_x) / eye_distance

        if abs(face_turn) < 0.1:
            angle = "front"
        elif face_turn > 0:
            angle = "slight right turn"
        else:
            angle = "slight left turn"

        return {
            "angle": angle,
            "eye_level": "neutral",
            "recommended_for_prompt": f"face {angle}, natural expression"
        }


def analyze_face_for_prompt(image_path: str) -> str:
    """
    Удобная функция для быстрого получения описания лица для промпта.

    Args:
        image_path: Путь к изображению

    Returns:
        Текстовое описание для промпта
    """
    analyzer = FaceAnalyzer()
    features = analyzer.analyze(image_path)
    return features.to_prompt_description()
