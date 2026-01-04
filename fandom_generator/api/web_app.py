"""
FastAPI Web Application for Fandom Image Generator
"""
import asyncio
import uuid
from pathlib import Path
from typing import Optional
import json

try:
    from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from ..orchestrator import FandomGeneratorPipeline
from ..config import config


# Хранилище задач в памяти (для production использовать Redis)
tasks_store = {}


class GenerationRequest(BaseModel):
    """Запрос на генерацию"""
    fandom_name: str
    num_scenes: int = 10
    generate_images: bool = False  # По умолчанию только промпты


class TaskStatus(BaseModel):
    """Статус задачи"""
    task_id: str
    status: str  # pending, processing, completed, failed
    progress: dict
    result: Optional[dict] = None
    error: Optional[str] = None


def create_app(
    upload_dir: str = "./uploads",
    output_dir: str = "./output"
) -> "FastAPI":
    """Создает FastAPI приложение"""

    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn python-multipart")

    app = FastAPI(
        title="Fandom Image Generator",
        description="Generate images in fandom style with AI agents and face preservation",
        version="0.1.0"
    )

    # Создаем директории
    Path(upload_dir).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # HTML страница
    @app.get("/", response_class=HTMLResponse)
    async def home():
        return """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fandom Image Generator</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            font-size: 2.5em;
            background: linear-gradient(45deg, #00d4ff, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .card {
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 500;
            color: #a0a0a0;
        }
        input[type="text"], input[type="number"], select {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            background: rgba(0,0,0,0.3);
            color: #fff;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        input:focus, select:focus {
            outline: none;
            border-color: #7c3aed;
        }
        .file-upload {
            border: 2px dashed rgba(255,255,255,0.3);
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        .file-upload:hover {
            border-color: #7c3aed;
            background: rgba(124,58,237,0.1);
        }
        .file-upload.has-file {
            border-color: #10b981;
            background: rgba(16,185,129,0.1);
        }
        #preview {
            max-width: 200px;
            max-height: 200px;
            margin-top: 15px;
            border-radius: 10px;
            display: none;
        }
        button {
            width: 100%;
            padding: 16px;
            border: none;
            border-radius: 10px;
            background: linear-gradient(45deg, #7c3aed, #00d4ff);
            color: #fff;
            font-size: 18px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(124,58,237,0.4);
        }
        button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        .progress-container {
            display: none;
            margin-top: 20px;
        }
        .progress-bar {
            height: 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            overflow: hidden;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(45deg, #7c3aed, #00d4ff);
            width: 0%;
            transition: width 0.5s;
        }
        .status-text {
            margin-top: 10px;
            color: #a0a0a0;
        }
        .results {
            display: none;
        }
        .prompt-card {
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 10px;
        }
        .prompt-title {
            color: #00d4ff;
            font-weight: 600;
            margin-bottom: 8px;
        }
        .prompt-text {
            font-size: 14px;
            line-height: 1.6;
            color: #d0d0d0;
        }
        .copy-btn {
            margin-top: 10px;
            padding: 8px 16px;
            font-size: 14px;
            width: auto;
        }
        .fandom-examples {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }
        .fandom-tag {
            padding: 6px 12px;
            background: rgba(124,58,237,0.3);
            border-radius: 20px;
            font-size: 14px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .fandom-tag:hover {
            background: rgba(124,58,237,0.5);
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-item {
            text-align: center;
            padding: 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
        }
        .stat-value {
            font-size: 24px;
            font-weight: 700;
            color: #00d4ff;
        }
        .stat-label {
            font-size: 12px;
            color: #a0a0a0;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎭 Fandom Image Generator</h1>

        <div class="card">
            <form id="generateForm">
                <div class="form-group">
                    <label>Фандом</label>
                    <input type="text" id="fandomName" placeholder="Например: Harry Potter, Naruto, Dragon Ball" required>
                    <div class="fandom-examples">
                        <span class="fandom-tag" onclick="setFandom('Harry Potter')">Harry Potter</span>
                        <span class="fandom-tag" onclick="setFandom('Naruto')">Naruto</span>
                        <span class="fandom-tag" onclick="setFandom('Dragon Ball')">Dragon Ball</span>
                        <span class="fandom-tag" onclick="setFandom('One Piece')">One Piece</span>
                        <span class="fandom-tag" onclick="setFandom('Marvel')">Marvel</span>
                        <span class="fandom-tag" onclick="setFandom('Star Wars')">Star Wars</span>
                    </div>
                </div>

                <div class="form-group">
                    <label>Ваше фото</label>
                    <div class="file-upload" id="dropZone" onclick="document.getElementById('photoFile').click()">
                        <input type="file" id="photoFile" accept="image/*" hidden>
                        <p>📷 Нажмите или перетащите фото</p>
                        <img id="preview" alt="Preview">
                    </div>
                </div>

                <div class="form-group">
                    <label>Количество сцен</label>
                    <input type="number" id="numScenes" value="10" min="1" max="20">
                </div>

                <button type="submit" id="submitBtn">✨ Сгенерировать промпты</button>
            </form>

            <div class="progress-container" id="progressContainer">
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill"></div>
                </div>
                <p class="status-text" id="statusText">Инициализация...</p>
            </div>
        </div>

        <div class="card results" id="resultsCard">
            <h2 style="margin-bottom: 20px;">📝 Результаты</h2>

            <div class="stats" id="statsContainer"></div>

            <div id="promptsList"></div>
        </div>
    </div>

    <script>
        const form = document.getElementById('generateForm');
        const photoFile = document.getElementById('photoFile');
        const preview = document.getElementById('preview');
        const dropZone = document.getElementById('dropZone');
        const progressContainer = document.getElementById('progressContainer');
        const progressFill = document.getElementById('progressFill');
        const statusText = document.getElementById('statusText');
        const resultsCard = document.getElementById('resultsCard');
        const submitBtn = document.getElementById('submitBtn');

        function setFandom(name) {
            document.getElementById('fandomName').value = name;
        }

        // File preview
        photoFile.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                preview.src = URL.createObjectURL(file);
                preview.style.display = 'block';
                dropZone.classList.add('has-file');
            }
        });

        // Drag and drop
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.style.borderColor = '#7c3aed';
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.style.borderColor = '';
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file && file.type.startsWith('image/')) {
                photoFile.files = e.dataTransfer.files;
                preview.src = URL.createObjectURL(file);
                preview.style.display = 'block';
                dropZone.classList.add('has-file');
            }
        });

        // Form submit
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const file = photoFile.files[0];
            if (!file) {
                alert('Пожалуйста, загрузите фото');
                return;
            }

            submitBtn.disabled = true;
            progressContainer.style.display = 'block';
            resultsCard.style.display = 'none';

            const formData = new FormData();
            formData.append('photo', file);
            formData.append('fandom_name', document.getElementById('fandomName').value);
            formData.append('num_scenes', document.getElementById('numScenes').value);

            try {
                // Start generation
                const response = await fetch('/api/generate', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (data.task_id) {
                    pollStatus(data.task_id);
                } else if (data.error) {
                    throw new Error(data.error);
                }
            } catch (error) {
                statusText.textContent = 'Ошибка: ' + error.message;
                submitBtn.disabled = false;
            }
        });

        async function pollStatus(taskId) {
            const stages = {
                'face_analysis': 15,
                'universe_research': 35,
                'scene_creation': 55,
                'prompt_engineering': 75,
                'prompt_critique': 90,
                'completed': 100
            };

            try {
                const response = await fetch(`/api/status/${taskId}`);
                const data = await response.json();

                const stage = data.progress?.stage || 'processing';
                const progress = stages[stage] || 50;

                progressFill.style.width = progress + '%';
                statusText.textContent = getStatusText(stage);

                if (data.status === 'completed') {
                    showResults(data.result);
                    submitBtn.disabled = false;
                } else if (data.status === 'failed') {
                    statusText.textContent = 'Ошибка: ' + (data.error || 'Unknown error');
                    submitBtn.disabled = false;
                } else {
                    setTimeout(() => pollStatus(taskId), 2000);
                }
            } catch (error) {
                statusText.textContent = 'Ошибка соединения';
                setTimeout(() => pollStatus(taskId), 5000);
            }
        }

        function getStatusText(stage) {
            const texts = {
                'face_analysis': '🔍 Анализ лица...',
                'universe_research': '🌍 Исследование вселенной...',
                'scene_creation': '🎬 Создание сцен...',
                'prompt_engineering': '✍️ Создание промптов...',
                'prompt_critique': '🔧 Улучшение промптов...',
                'completed': '✅ Готово!'
            };
            return texts[stage] || '⏳ Обработка...';
        }

        function showResults(result) {
            progressContainer.style.display = 'none';
            resultsCard.style.display = 'block';

            // Stats
            const stats = result.statistics || {};
            document.getElementById('statsContainer').innerHTML = `
                <div class="stat-item">
                    <div class="stat-value">${result.prompts?.length || 0}</div>
                    <div class="stat-label">Сцен</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${stats.style_type || 'mixed'}</div>
                    <div class="stat-label">Стиль</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${(stats.critique_score * 100).toFixed(0)}%</div>
                    <div class="stat-label">Качество</div>
                </div>
            `;

            // Prompts
            const promptsList = document.getElementById('promptsList');
            promptsList.innerHTML = '';

            (result.prompts || []).forEach((prompt, i) => {
                const card = document.createElement('div');
                card.className = 'prompt-card';
                card.innerHTML = `
                    <div class="prompt-title">Сцена ${prompt.scene_id || i + 1}</div>
                    <div class="prompt-text">${prompt.main_prompt || ''}</div>
                    <button class="copy-btn" onclick="copyPrompt(this, '${encodeURIComponent(prompt.main_prompt || '')}')">
                        📋 Копировать
                    </button>
                `;
                promptsList.appendChild(card);
            });
        }

        function copyPrompt(btn, text) {
            navigator.clipboard.writeText(decodeURIComponent(text));
            btn.textContent = '✅ Скопировано!';
            setTimeout(() => btn.textContent = '📋 Копировать', 2000);
        }
    </script>
</body>
</html>
        """

    # API endpoints
    @app.post("/api/generate")
    async def generate(
        background_tasks: BackgroundTasks,
        photo: UploadFile = File(...),
        fandom_name: str = Form(...),
        num_scenes: int = Form(10)
    ):
        """Запускает генерацию промптов"""
        task_id = str(uuid.uuid4())

        # Сохраняем фото
        photo_path = Path(upload_dir) / f"{task_id}_{photo.filename}"
        with open(photo_path, "wb") as f:
            content = await photo.read()
            f.write(content)

        # Создаем задачу
        tasks_store[task_id] = {
            "status": "pending",
            "progress": {},
            "result": None,
            "error": None
        }

        # Запускаем в фоне
        background_tasks.add_task(
            run_generation,
            task_id,
            fandom_name,
            str(photo_path),
            num_scenes
        )

        return {"task_id": task_id, "status": "started"}

    @app.get("/api/status/{task_id}")
    async def get_status(task_id: str):
        """Получает статус задачи"""
        if task_id not in tasks_store:
            raise HTTPException(status_code=404, detail="Task not found")

        return tasks_store[task_id]

    async def run_generation(
        task_id: str,
        fandom_name: str,
        photo_path: str,
        num_scenes: int
    ):
        """Фоновая задача генерации"""
        try:
            tasks_store[task_id]["status"] = "processing"

            pipeline = FandomGeneratorPipeline()

            def progress_callback(status):
                tasks_store[task_id]["progress"] = status

            result = await pipeline.run_prompts_only(
                fandom_name=fandom_name,
                user_image_path=photo_path,
                num_scenes=num_scenes
            )

            if result.success:
                tasks_store[task_id]["status"] = "completed"
                tasks_store[task_id]["progress"] = {"stage": "completed"}
                tasks_store[task_id]["result"] = {
                    "prompts": result.prompts,
                    "statistics": result.statistics
                }
            else:
                tasks_store[task_id]["status"] = "failed"
                tasks_store[task_id]["error"] = "; ".join(result.errors)

        except Exception as e:
            tasks_store[task_id]["status"] = "failed"
            tasks_store[task_id]["error"] = str(e)

    return app


def run_server(host: str = "0.0.0.0", port: int = 8000):
    """Запускает сервер"""
    import uvicorn
    app = create_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
