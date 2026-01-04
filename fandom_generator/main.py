"""
Fandom Image Generator - Main Entry Point
Генератор изображений в стиле фандомов с AI агентами
"""
import asyncio
import argparse
from pathlib import Path

from .orchestrator import FandomGeneratorPipeline
from .config import config


async def main():
    """Главная функция CLI"""
    parser = argparse.ArgumentParser(
        description="Generate fandom images with AI agents and face preservation"
    )

    parser.add_argument(
        "fandom",
        type=str,
        help="Name of the fandom (e.g., 'Harry Potter', 'Dragon Ball', 'Naruto')"
    )

    parser.add_argument(
        "photo",
        type=str,
        help="Path to user's photo"
    )

    parser.add_argument(
        "--scenes", "-n",
        type=int,
        default=10,
        help="Number of scenes to generate (default: 10)"
    )

    parser.add_argument(
        "--output", "-o",
        type=str,
        default="./output",
        help="Output directory for results"
    )

    parser.add_argument(
        "--prompts-only",
        action="store_true",
        help="Generate only prompts without images"
    )

    parser.add_argument(
        "--export-json",
        type=str,
        help="Export prompts to JSON file"
    )

    args = parser.parse_args()

    # Проверяем входные данные
    photo_path = Path(args.photo)
    if not photo_path.exists():
        print(f"Error: Photo not found: {args.photo}")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Инициализация пайплайна
    print(f"Initializing Fandom Generator for '{args.fandom}'...")
    pipeline = FandomGeneratorPipeline()

    # Callback для прогресса
    def progress_callback(status):
        stage = status.get("stage", "unknown")
        data = status.get("data", {})
        print(f"  [{stage}] {data.get('status', '')}")

    # Запуск
    print("\nStarting generation pipeline...")
    print("-" * 50)

    if args.prompts_only:
        result = await pipeline.run_prompts_only(
            fandom_name=args.fandom,
            user_image_path=photo_path,
            num_scenes=args.scenes
        )
    else:
        result = await pipeline.run(
            fandom_name=args.fandom,
            user_image_path=photo_path,
            num_scenes=args.scenes,
            callback=progress_callback
        )

    print("-" * 50)

    # Результаты
    if result.success:
        print("\n✓ Generation completed successfully!")
        print(f"\nStatistics:")
        print(f"  - Fandom style: {result.statistics.get('style_type', 'unknown')}")
        print(f"  - Scenes generated: {result.statistics.get('num_scenes', 0)}")
        print(f"  - Critique score: {result.statistics.get('critique_score', 0):.2f}")

        if result.images:
            gen_stats = result.statistics.get("generation_stats", {})
            print(f"\nImage Generation:")
            print(f"  - Successful: {gen_stats.get('successful', 0)}")
            print(f"  - Average similarity: {gen_stats.get('average_similarity', 0):.2f}")
            print(f"  - Meets threshold: {gen_stats.get('meets_threshold', 0)}")

        # Экспорт промптов
        if args.export_json:
            pipeline.export_prompts(result, args.export_json)
            print(f"\nPrompts exported to: {args.export_json}")

        # Показываем примеры промптов
        print("\n" + "=" * 50)
        print("GENERATED PROMPTS:")
        print("=" * 50)

        for i, prompt in enumerate(result.prompts[:3], 1):
            print(f"\n[Scene {prompt.get('scene_id', i)}]")
            print(f"Prompt: {prompt.get('main_prompt', '')[:200]}...")
            if prompt.get('critique_score'):
                print(f"Score: {prompt.get('critique_score', 0):.2f}")

        if len(result.prompts) > 3:
            print(f"\n... and {len(result.prompts) - 3} more prompts")

    else:
        print("\n✗ Generation failed!")
        for error in result.errors:
            print(f"  Error: {error}")
        return 1

    return 0


def run():
    """Entry point для консольной команды"""
    import sys
    sys.exit(asyncio.run(main()))


if __name__ == "__main__":
    run()
