"""
FastAPI Web Application for Fandom Image Generator
ФОТОРЕАЛИСТИЧНЫЙ стиль, 16:9, Nano Banana 3 Pro
С кнопкой "Улучшить" для итеративной оптимизации промптов
"""
import asyncio
import uuid
from pathlib import Path
from typing import Optional
import json

try:
    from fastapi import FastAPI, File, UploadFile, Form, HTTPException, BackgroundTasks
    from fastapi.responses import HTMLResponse, JSONResponse
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

from ..orchestrator import FandomGeneratorPipeline
from ..agents import PromptOptimizerAgent
from ..config import config


# Хранилище задач в памяти
tasks_store = {}
prompts_store = {}  # Хранилище промптов для оптимизации


class OptimizeRequest(BaseModel):
    """Запрос на оптимизацию промпта"""
    prompt_id: str
    num_iterations: int = 3


def create_app(
    upload_dir: str = "./uploads",
    output_dir: str = "./output"
) -> "FastAPI":
    """Создает FastAPI приложение"""

    if not FASTAPI_AVAILABLE:
        raise ImportError("FastAPI not installed. Run: pip install fastapi uvicorn python-multipart")

    app = FastAPI(
        title="Fandom Image Generator",
        description="Photorealistic fandom images with AI optimization",
        version="0.2.0"
    )

    Path(upload_dir).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    @app.get("/", response_class=HTMLResponse)
    async def home():
        return """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fandom Image Generator - Photorealistic</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #fff;
            padding: 20px;
        }
        .container { max-width: 900px; margin: 0 auto; }
        h1 {
            text-align: center;
            margin-bottom: 10px;
            font-size: 2.5em;
            background: linear-gradient(45deg, #00d4ff, #7c3aed);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .subtitle {
            text-align: center;
            color: #888;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .badge {
            display: inline-block;
            padding: 4px 10px;
            background: rgba(0,212,255,0.2);
            border-radius: 20px;
            font-size: 12px;
            color: #00d4ff;
            margin: 0 5px;
        }
        .card {
            background: rgba(255,255,255,0.1);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
        }
        .form-group { margin-bottom: 20px; }
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
        .file-upload:hover { border-color: #7c3aed; background: rgba(124,58,237,0.1); }
        .file-upload.has-file { border-color: #10b981; background: rgba(16,185,129,0.1); }
        #preview {
            max-width: 200px;
            max-height: 200px;
            margin-top: 15px;
            border-radius: 10px;
            display: none;
        }
        button {
            padding: 16px 32px;
            border: none;
            border-radius: 10px;
            background: linear-gradient(45deg, #7c3aed, #00d4ff);
            color: #fff;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(124,58,237,0.4);
        }
        button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .btn-full { width: 100%; }
        .btn-optimize {
            background: linear-gradient(45deg, #f59e0b, #ef4444);
            margin-top: 10px;
        }
        .btn-secondary {
            background: rgba(255,255,255,0.1);
            border: 2px solid rgba(255,255,255,0.2);
        }
        .progress-container { display: none; margin-top: 20px; }
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
        .status-text { margin-top: 10px; color: #a0a0a0; }
        .results { display: none; }
        .prompt-card {
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 15px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .prompt-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        .prompt-title {
            color: #00d4ff;
            font-weight: 600;
            font-size: 16px;
        }
        .prompt-score {
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        .score-high { background: rgba(16,185,129,0.3); color: #10b981; }
        .score-medium { background: rgba(245,158,11,0.3); color: #f59e0b; }
        .score-low { background: rgba(239,68,68,0.3); color: #ef4444; }
        .prompt-text {
            font-size: 14px;
            line-height: 1.6;
            color: #d0d0d0;
            background: rgba(0,0,0,0.3);
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 12px;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .prompt-actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        .prompt-actions button {
            padding: 8px 16px;
            font-size: 14px;
        }
        .optimization-panel {
            background: rgba(245,158,11,0.1);
            border: 1px solid rgba(245,158,11,0.3);
            border-radius: 10px;
            padding: 15px;
            margin-top: 10px;
            display: none;
        }
        .optimization-panel.active { display: block; }
        .iteration-history {
            margin-top: 10px;
            max-height: 200px;
            overflow-y: auto;
        }
        .iteration-item {
            padding: 8px;
            background: rgba(0,0,0,0.2);
            border-radius: 6px;
            margin-bottom: 5px;
            font-size: 13px;
        }
        .iteration-item.improved { border-left: 3px solid #10b981; }
        .iteration-item.not-improved { border-left: 3px solid #ef4444; }
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
        .fandom-tag:hover { background: rgba(124,58,237,0.5); }
        .stats {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
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
        .iterations-input {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 10px;
        }
        .iterations-input input {
            width: 80px;
            text-align: center;
        }
        .iterations-input label {
            margin: 0;
            color: #f59e0b;
        }
        @media (max-width: 600px) {
            .stats { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Fandom Image Generator</h1>
        <div class="subtitle">
            <span class="badge">PHOTOREALISTIC</span>
            <span class="badge">16:9</span>
            <span class="badge">Nano Banana 3 Pro</span>
        </div>

        <div class="card">
            <form id="generateForm">
                <div class="form-group">
                    <label>Фандом</label>
                    <input type="text" id="fandomName" placeholder="Например: Naruto, Harry Potter, Dragon Ball" required>
                    <div class="fandom-examples">
                        <span class="fandom-tag" onclick="setFandom('Naruto')">Naruto</span>
                        <span class="fandom-tag" onclick="setFandom('Dragon Ball')">Dragon Ball</span>
                        <span class="fandom-tag" onclick="setFandom('One Piece')">One Piece</span>
                        <span class="fandom-tag" onclick="setFandom('Harry Potter')">Harry Potter</span>
                        <span class="fandom-tag" onclick="setFandom('Marvel')">Marvel</span>
                        <span class="fandom-tag" onclick="setFandom('Star Wars')">Star Wars</span>
                        <span class="fandom-tag" onclick="setFandom('Game of Thrones')">Game of Thrones</span>
                    </div>
                </div>

                <div class="form-group">
                    <label>Ваше фото</label>
                    <div class="file-upload" id="dropZone" onclick="document.getElementById('photoFile').click()">
                        <input type="file" id="photoFile" accept="image/*" hidden>
                        <p>Нажмите или перетащите фото</p>
                        <img id="preview" alt="Preview">
                    </div>
                </div>

                <div class="form-group">
                    <label>Количество сцен</label>
                    <input type="number" id="numScenes" value="10" min="1" max="20">
                </div>

                <button type="submit" id="submitBtn" class="btn-full">Сгенерировать промпты</button>
            </form>

            <div class="progress-container" id="progressContainer">
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill"></div>
                </div>
                <p class="status-text" id="statusText">Инициализация...</p>
            </div>
        </div>

        <div class="card results" id="resultsCard">
            <h2 style="margin-bottom: 20px;">Результаты (ФОТОРЕАЛИСТИЧНЫЕ промпты)</h2>

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

        let currentPrompts = [];
        let faceDescription = '';

        function setFandom(name) {
            document.getElementById('fandomName').value = name;
        }

        // File handling
        photoFile.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                preview.src = URL.createObjectURL(file);
                preview.style.display = 'block';
                dropZone.classList.add('has-file');
            }
        });

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
                'face_analysis': 'Анализ лица...',
                'universe_research': 'Исследование вселенной...',
                'scene_creation': 'Создание сцен...',
                'prompt_engineering': 'Создание ФОТОРЕАЛИСТИЧНЫХ промптов...',
                'prompt_critique': 'Критика и улучшение...',
                'completed': 'Готово!'
            };
            return texts[stage] || 'Обработка...';
        }

        function showResults(result) {
            progressContainer.style.display = 'none';
            resultsCard.style.display = 'block';

            currentPrompts = result.prompts || [];
            faceDescription = result.statistics?.face_description || '';

            const stats = result.statistics || {};
            document.getElementById('statsContainer').innerHTML = `
                <div class="stat-item">
                    <div class="stat-value">${currentPrompts.length}</div>
                    <div class="stat-label">Сцен</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">PHOTO</div>
                    <div class="stat-label">Стиль</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">16:9</div>
                    <div class="stat-label">Формат</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value">${((stats.critique_score || 0) * 100).toFixed(0)}%</div>
                    <div class="stat-label">Качество</div>
                </div>
            `;

            renderPrompts();
        }

        function renderPrompts() {
            const promptsList = document.getElementById('promptsList');
            promptsList.innerHTML = '';

            currentPrompts.forEach((prompt, i) => {
                const score = prompt.quality_score_estimate || prompt.critique_score || 0.7;
                const scoreClass = score >= 0.85 ? 'score-high' : score >= 0.7 ? 'score-medium' : 'score-low';

                const card = document.createElement('div');
                card.className = 'prompt-card';
                card.id = `prompt-${i}`;
                card.innerHTML = `
                    <div class="prompt-header">
                        <span class="prompt-title">Сцена ${prompt.scene_id || i + 1}</span>
                        <span class="prompt-score ${scoreClass}">${(score * 100).toFixed(0)}%</span>
                    </div>
                    <div class="prompt-text">${prompt.main_prompt || ''}</div>
                    <div class="prompt-actions">
                        <button onclick="copyPrompt(${i})">Копировать</button>
                        <button class="btn-optimize" onclick="toggleOptimize(${i})">Улучшить</button>
                    </div>
                    <div class="optimization-panel" id="optimize-panel-${i}">
                        <div class="iterations-input">
                            <label>Итерации:</label>
                            <input type="number" id="iterations-${i}" value="3" min="1" max="10">
                            <button onclick="startOptimization(${i})">Запустить</button>
                        </div>
                        <div class="iteration-history" id="history-${i}"></div>
                    </div>
                `;
                promptsList.appendChild(card);
            });
        }

        function copyPrompt(index) {
            const prompt = currentPrompts[index];
            navigator.clipboard.writeText(prompt.main_prompt || '');
            event.target.textContent = 'Скопировано!';
            setTimeout(() => event.target.textContent = 'Копировать', 2000);
        }

        function toggleOptimize(index) {
            const panel = document.getElementById(`optimize-panel-${index}`);
            panel.classList.toggle('active');
        }

        async function startOptimization(index) {
            const iterations = parseInt(document.getElementById(`iterations-${index}`).value) || 3;
            const historyDiv = document.getElementById(`history-${index}`);
            const prompt = currentPrompts[index];

            historyDiv.innerHTML = '<div class="iteration-item">Запуск оптимизации...</div>';

            try {
                const response = await fetch('/api/optimize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        prompt: prompt.main_prompt,
                        face_description: faceDescription,
                        num_iterations: iterations
                    })
                });

                const result = await response.json();

                if (result.success) {
                    // Обновляем промпт
                    currentPrompts[index].main_prompt = result.optimized_prompt;
                    currentPrompts[index].quality_score_estimate = result.final_score;

                    // Показываем историю
                    historyDiv.innerHTML = '';
                    (result.history || []).forEach((iter, i) => {
                        const isImproved = iter.is_better;
                        historyDiv.innerHTML += `
                            <div class="iteration-item ${isImproved ? 'improved' : 'not-improved'}">
                                <strong>Итерация ${iter.iteration}:</strong>
                                Score: ${(iter.original_score?.total * 100).toFixed(0)}% → ${(iter.improved_score?.total * 100).toFixed(0)}%
                                ${isImproved ? '✓ Улучшено' : '✗ Не улучшено'}
                            </div>
                        `;
                    });

                    historyDiv.innerHTML += `
                        <div class="iteration-item improved" style="background: rgba(16,185,129,0.2)">
                            <strong>Финальный score: ${(result.final_score * 100).toFixed(0)}%</strong>
                            ${result.reached_target ? '🎯 Цель достигнута!' : ''}
                        </div>
                    `;

                    // Перерисовываем промпты
                    renderPrompts();
                } else {
                    historyDiv.innerHTML = `<div class="iteration-item not-improved">Ошибка: ${result.error}</div>`;
                }
            } catch (error) {
                historyDiv.innerHTML = `<div class="iteration-item not-improved">Ошибка: ${error.message}</div>`;
            }
        }
    </script>
</body>
</html>
        """

    @app.post("/api/generate")
    async def generate(
        background_tasks: BackgroundTasks,
        photo: UploadFile = File(...),
        fandom_name: str = Form(...),
        num_scenes: int = Form(10)
    ):
        """Запускает генерацию ФОТОРЕАЛИСТИЧНЫХ промптов"""
        task_id = str(uuid.uuid4())

        photo_path = Path(upload_dir) / f"{task_id}_{photo.filename}"
        with open(photo_path, "wb") as f:
            content = await photo.read()
            f.write(content)

        tasks_store[task_id] = {
            "status": "pending",
            "progress": {},
            "result": None,
            "error": None
        }

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

    @app.post("/api/optimize")
    async def optimize_prompt(
        prompt: str = Form(...),
        face_description: str = Form(""),
        num_iterations: int = Form(3)
    ):
        """Итеративно улучшает промпт"""
        try:
            optimizer = PromptOptimizerAgent(
                max_iterations=num_iterations,
                min_improvement=0.03,
                target_score=0.95
            )

            result = await optimizer.run(
                prompt=prompt,
                face_description=face_description,
                num_iterations=num_iterations
            )

            if result.success:
                return {
                    "success": True,
                    "original_prompt": result.data["original_prompt"],
                    "optimized_prompt": result.data["optimized_prompt"],
                    "final_score": result.data["final_score"],
                    "iterations_used": result.data["iterations_used"],
                    "history": result.data["history"],
                    "reached_target": result.data["reached_target"]
                }
            else:
                return {"success": False, "error": result.error}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # Альтернативный endpoint для JSON body
    @app.post("/api/optimize-json")
    async def optimize_prompt_json(request: dict):
        """Итеративно улучшает промпт (JSON body)"""
        try:
            optimizer = PromptOptimizerAgent(
                max_iterations=request.get("num_iterations", 3),
                min_improvement=0.03,
                target_score=0.95
            )

            result = await optimizer.run(
                prompt=request.get("prompt", ""),
                face_description=request.get("face_description", ""),
                num_iterations=request.get("num_iterations", 3)
            )

            if result.success:
                return {
                    "success": True,
                    "original_prompt": result.data["original_prompt"],
                    "optimized_prompt": result.data["optimized_prompt"],
                    "final_score": result.data["final_score"],
                    "iterations_used": result.data["iterations_used"],
                    "history": result.data["history"],
                    "reached_target": result.data["reached_target"]
                }
            else:
                return {"success": False, "error": result.error}

        except Exception as e:
            return {"success": False, "error": str(e)}

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
                    "statistics": {
                        **result.statistics,
                        "style": "photorealistic",
                        "aspect_ratio": "16:9"
                    }
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
