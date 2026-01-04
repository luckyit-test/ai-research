"""
Quality Checker - проверка качества сгенерированных изображений
"""
import numpy as np
from typing import Optional, Union
from pathlib import Path
from dataclasses import dataclass

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


@dataclass
class QualityReport:
    """Отчет о качестве изображения"""
    face_similarity: float
    image_quality: float  # 0-1
    style_consistency: float  # 0-1
    overall_score: float
    issues: list[str]
    recommendations: list[str]


class QualityChecker:
    """
    Проверяет качество сгенерированных изображений.
    """

    def __init__(self, face_embeddings=None):
        self.face_embeddings = face_embeddings

    def check_image(
        self,
        generated_image: Union[np.ndarray, str, Path],
        original_face: Union[np.ndarray, str, Path],
        target_style: str = "photorealistic"
    ) -> QualityReport:
        """
        Проверяет качество сгенерированного изображения.

        Args:
            generated_image: Сгенерированное изображение
            original_face: Оригинальное фото пользователя
            target_style: Целевой стиль (photorealistic, anime, etc.)
        """
        issues = []
        recommendations = []

        # Загрузка изображений
        if isinstance(generated_image, (str, Path)):
            gen_img = cv2.imread(str(generated_image)) if CV2_AVAILABLE else None
        else:
            gen_img = generated_image

        # Проверка сходства лица
        face_similarity = self._check_face_similarity(gen_img, original_face)
        if face_similarity < 0.6:
            issues.append("Low face similarity")
            recommendations.append("Apply face swap with higher quality settings")
        elif face_similarity < 0.75:
            issues.append("Moderate face similarity - could be improved")
            recommendations.append("Consider using iterative face swap")

        # Проверка качества изображения
        image_quality = self._check_image_quality(gen_img)
        if image_quality < 0.5:
            issues.append("Low image quality")
            recommendations.append("Regenerate with higher quality settings")

        # Проверка соответствия стилю
        style_consistency = self._check_style_consistency(gen_img, target_style)
        if style_consistency < 0.7:
            issues.append(f"Style doesn't match {target_style}")
            recommendations.append("Adjust style parameters in prompt")

        # Общий score
        overall_score = (
            face_similarity * 0.5 +  # Лицо - самое важное
            image_quality * 0.25 +
            style_consistency * 0.25
        )

        return QualityReport(
            face_similarity=face_similarity,
            image_quality=image_quality,
            style_consistency=style_consistency,
            overall_score=overall_score,
            issues=issues,
            recommendations=recommendations
        )

    def _check_face_similarity(
        self,
        generated_image: np.ndarray,
        original_face: Union[np.ndarray, str, Path]
    ) -> float:
        """Проверяет сходство лица"""
        if self.face_embeddings is None:
            return 0.5  # Нет модели - возвращаем среднее

        try:
            _, similarity = self.face_embeddings.verify_similarity(
                original_face, generated_image
            )
            return similarity
        except Exception:
            return 0.0

    def _check_image_quality(self, image: np.ndarray) -> float:
        """
        Проверяет качество изображения.
        Использует простые эвристики без ML моделей.
        """
        if image is None or not CV2_AVAILABLE:
            return 0.5

        score = 1.0

        # Проверка размера
        h, w = image.shape[:2]
        if w < 512 or h < 512:
            score -= 0.2
        if w > 2048 and h > 2048:
            score += 0.1  # Бонус за высокое разрешение

        # Проверка размытости (Laplacian variance)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()

        if laplacian_var < 100:
            score -= 0.3  # Сильно размыто
        elif laplacian_var < 500:
            score -= 0.1  # Немного размыто

        # Проверка контраста
        contrast = gray.std()
        if contrast < 30:
            score -= 0.2  # Низкий контраст
        elif contrast > 80:
            score += 0.05  # Хороший контраст

        return max(0, min(1, score))

    def _check_style_consistency(self, image: np.ndarray, target_style: str) -> float:
        """
        Проверяет соответствие стилю.
        Базовая проверка без ML моделей.
        """
        if image is None or not CV2_AVAILABLE:
            return 0.5

        # Для anime стиля проверяем насыщенность цветов
        if target_style in ["anime", "animated"]:
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            saturation = hsv[:, :, 1].mean()

            # Anime обычно имеет высокую насыщенность
            if saturation > 100:
                return 0.9
            elif saturation > 60:
                return 0.7
            else:
                return 0.5

        # Для photorealistic проверяем естественность цветов
        elif target_style == "photorealistic" or target_style == "live_action":
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            saturation = hsv[:, :, 1].mean()

            # Фото обычно имеют умеренную насыщенность
            if 40 < saturation < 120:
                return 0.9
            else:
                return 0.6

        return 0.7

    def batch_check(
        self,
        images: list[dict],
        original_face: Union[np.ndarray, str, Path],
        target_style: str
    ) -> dict:
        """
        Проверяет качество batch изображений.

        Returns:
            Статистику по всему batch
        """
        reports = []

        for img_data in images:
            image = img_data.get("image")
            if image is not None:
                report = self.check_image(image, original_face, target_style)
                reports.append(report)

        if not reports:
            return {"error": "No images to check"}

        return {
            "total_images": len(reports),
            "average_face_similarity": sum(r.face_similarity for r in reports) / len(reports),
            "average_quality": sum(r.image_quality for r in reports) / len(reports),
            "average_style": sum(r.style_consistency for r in reports) / len(reports),
            "average_overall": sum(r.overall_score for r in reports) / len(reports),
            "high_quality_count": sum(1 for r in reports if r.overall_score >= 0.8),
            "needs_improvement": sum(1 for r in reports if r.overall_score < 0.6),
            "common_issues": self._get_common_issues(reports)
        }

    def _get_common_issues(self, reports: list[QualityReport]) -> list[str]:
        """Находит наиболее частые проблемы"""
        issue_counts = {}
        for report in reports:
            for issue in report.issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1

        # Сортируем по частоте
        sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        return [issue for issue, count in sorted_issues if count >= len(reports) * 0.3]
