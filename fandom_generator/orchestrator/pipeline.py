"""
Fandom Generator Pipeline - оркестрация всех агентов
Главный пайплайн для генерации изображений
"""
import asyncio
from typing import Optional, Union
from pathlib import Path
from dataclasses import dataclass, field
import json

from ..agents import (
    FaceAnalyzerAgent,
    UniverseResearcherAgent,
    SceneArchitectAgent,
    PromptEngineerAgent,
    PromptCriticAgent,
    ImageGeneratorAgent,
    AgentResult
)
from ..face_processing import FaceSwapper, FaceEnhancer, FaceEmbeddings
from ..config import Config, config


@dataclass
class PipelineResult:
    """Результат работы пайплайна"""
    success: bool
    images: list[dict] = field(default_factory=list)
    prompts: list[dict] = field(default_factory=list)
    statistics: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class FandomGeneratorPipeline:
    """
    Главный пайплайн для генерации изображений в стиле фандомов.

    Последовательность:
    1. Face Analyzer -> анализ лица пользователя
    2. Universe Researcher -> исследование фандома
    3. Scene Architect -> создание 10 культовых сцен
    4. Prompt Engineer -> создание промптов
    5. Prompt Critic -> критика и улучшение промптов
    6. Image Generator -> генерация + face swap
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        api_key: Optional[str] = None
    ):
        self.config = config or globals()["config"]
        self.api_key = api_key or self.config.anthropic_api_key

        # Инициализация агентов
        self._init_agents()

        # Инициализация face processing
        self._init_face_processing()

    def _init_agents(self):
        """Инициализация всех агентов"""
        agent_kwargs = {
            "api_key": self.api_key,
            "model": self.config.agent.model,
            "max_tokens": self.config.agent.max_tokens,
            "temperature": self.config.agent.temperature
        }

        self.face_analyzer = FaceAnalyzerAgent(**agent_kwargs)
        self.universe_researcher = UniverseResearcherAgent(**agent_kwargs)
        self.scene_architect = SceneArchitectAgent(**agent_kwargs)
        self.prompt_engineer = PromptEngineerAgent(**agent_kwargs)
        self.prompt_critic = PromptCriticAgent(
            min_acceptable_score=self.config.agent.min_critic_score,
            max_iterations=self.config.agent.max_critic_iterations,
            **agent_kwargs
        )
        self.image_generator = None  # Инициализируется отдельно

    def _init_face_processing(self):
        """Инициализация обработки лиц"""
        try:
            self.embeddings = FaceEmbeddings(
                det_size=self.config.face.det_size,
                det_thresh=self.config.face.det_thresh
            )

            # Face swapper требует модель - пропускаем если нет
            self.face_swapper = None

            # Face enhancer
            self.face_enhancer = None
            if self.config.face.use_gfpgan or self.config.face.use_codeformer:
                try:
                    self.face_enhancer = FaceEnhancer(
                        use_gfpgan=self.config.face.use_gfpgan,
                        use_codeformer=self.config.face.use_codeformer
                    )
                except Exception as e:
                    print(f"Face enhancer init failed: {e}")

        except Exception as e:
            print(f"Face processing init failed: {e}")
            self.embeddings = None
            self.face_swapper = None
            self.face_enhancer = None

    async def run(
        self,
        fandom_name: str,
        user_image_path: Union[str, Path],
        num_scenes: int = 10,
        generate_images: bool = True,
        callback=None
    ) -> PipelineResult:
        """
        Запускает полный пайплайн генерации.

        Args:
            fandom_name: Название фандома
            user_image_path: Путь к фото пользователя
            num_scenes: Количество сцен для генерации
            generate_images: Генерировать ли изображения (или только промпты)
            callback: Функция обратного вызова для прогресса

        Returns:
            PipelineResult с результатами
        """
        errors = []
        results = {}

        def report_progress(stage: str, data: dict = None):
            if callback:
                callback({"stage": stage, "data": data})
            print(f"[Pipeline] Stage: {stage}")

        try:
            # Stage 1: Face Analysis
            report_progress("face_analysis", {"status": "started"})
            face_result = await self.face_analyzer.run(
                image_path=str(user_image_path)
            )

            if not face_result.success:
                return PipelineResult(
                    success=False,
                    errors=[f"Face analysis failed: {face_result.error}"]
                )

            results["face_data"] = face_result.data
            report_progress("face_analysis", {"status": "completed"})

            # Stage 2: Universe Research
            report_progress("universe_research", {"status": "started"})
            universe_result = await self.universe_researcher.run(
                fandom_name=fandom_name
            )

            if not universe_result.success:
                return PipelineResult(
                    success=False,
                    errors=[f"Universe research failed: {universe_result.error}"]
                )

            results["universe_data"] = universe_result.data
            report_progress("universe_research", {
                "status": "completed",
                "style_type": universe_result.data.get("style_type")
            })

            # Stage 3: Scene Architecture
            report_progress("scene_creation", {"status": "started"})
            scenes_result = await self.scene_architect.run(
                universe_data=results["universe_data"],
                face_data=results["face_data"],
                num_scenes=num_scenes
            )

            if not scenes_result.success:
                return PipelineResult(
                    success=False,
                    errors=[f"Scene creation failed: {scenes_result.error}"]
                )

            results["scenes_data"] = scenes_result.data
            report_progress("scene_creation", {
                "status": "completed",
                "num_scenes": len(scenes_result.data.get("scenes", []))
            })

            # Stage 4: Prompt Engineering
            report_progress("prompt_engineering", {"status": "started"})
            prompts_result = await self.prompt_engineer.run(
                scenes_data=results["scenes_data"],
                face_data=results["face_data"],
                universe_data=results["universe_data"]
            )

            if not prompts_result.success:
                return PipelineResult(
                    success=False,
                    errors=[f"Prompt engineering failed: {prompts_result.error}"]
                )

            results["prompts_data"] = prompts_result.data
            report_progress("prompt_engineering", {"status": "completed"})

            # Stage 5: Prompt Criticism
            report_progress("prompt_critique", {"status": "started"})
            critique_result = await self.prompt_critic.run(
                prompts_data=results["prompts_data"],
                face_data=results["face_data"],
                universe_data=results["universe_data"],
                scenes_data=results["scenes_data"]
            )

            if not critique_result.success:
                errors.append(f"Prompt critique had issues: {critique_result.error}")
                # Используем оригинальные промпты если критика не удалась
                final_prompts = results["prompts_data"].get("prompts", [])
            else:
                results["critique_data"] = critique_result.data
                final_prompts = critique_result.data.get("final_prompts", [])

            report_progress("prompt_critique", {
                "status": "completed",
                "final_score": critique_result.data.get("final_average_score", 0) if critique_result.success else 0
            })

            # Stage 6: Image Generation (optional)
            generated_images = []
            if generate_images:
                report_progress("image_generation", {"status": "started"})

                # Инициализируем генератор
                self.image_generator = ImageGeneratorAgent(
                    face_swapper=self.face_swapper,
                    face_enhancer=self.face_enhancer,
                    embeddings=self.embeddings,
                    target_similarity=self.config.face.target_similarity_score
                )

                generation_result = await self.image_generator.run(
                    final_prompts=final_prompts,
                    user_image_path=str(user_image_path),
                    face_embedding=results["face_data"].get("face_embedding", []),
                    generation_config=results["prompts_data"].get("generation_config", {})
                )

                if generation_result.success:
                    generated_images = generation_result.data.get("generated_images", [])
                    results["generation_stats"] = generation_result.data.get("statistics", {})
                else:
                    errors.append(f"Image generation had issues: {generation_result.error}")

                report_progress("image_generation", {
                    "status": "completed",
                    "stats": results.get("generation_stats", {})
                })

            report_progress("completed", {"success": True})

            return PipelineResult(
                success=True,
                images=generated_images,
                prompts=final_prompts,
                statistics={
                    "num_scenes": len(final_prompts),
                    "style_type": results["universe_data"].get("style_type"),
                    "critique_score": critique_result.data.get("final_average_score", 0) if critique_result.success else 0,
                    "generation_stats": results.get("generation_stats", {}),
                    "face_description": results["face_data"].get("basic_description")
                },
                errors=errors,
                metadata={
                    "fandom": fandom_name,
                    "user_image": str(user_image_path),
                    "pipeline_data": results
                }
            )

        except Exception as e:
            report_progress("error", {"error": str(e)})
            return PipelineResult(
                success=False,
                errors=[str(e)]
            )

    async def run_prompts_only(
        self,
        fandom_name: str,
        user_image_path: Union[str, Path],
        num_scenes: int = 10
    ) -> PipelineResult:
        """
        Генерирует только промпты без изображений.
        Полезно для тестирования и предпросмотра.
        """
        return await self.run(
            fandom_name=fandom_name,
            user_image_path=user_image_path,
            num_scenes=num_scenes,
            generate_images=False
        )

    def export_prompts(self, result: PipelineResult, output_path: str):
        """Экспортирует промпты в JSON файл"""
        export_data = {
            "fandom": result.metadata.get("fandom"),
            "style_type": result.statistics.get("style_type"),
            "face_description": result.statistics.get("face_description"),
            "prompts": result.prompts,
            "statistics": result.statistics
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
