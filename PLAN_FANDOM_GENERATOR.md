# План разработки: Fandom Image Generator с максимальным сходством лица

## Проблема
- Текущее сходство лица ~70%
- Нужно достичь 90-95%+ сходства при генерации в Niji Banania 3 Pro

## Архитектура системы (Multi-Agent Pipeline)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INPUT                                      │
│                    [Фандом] + [Фото пользователя]                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AGENT 1: Face Analyzer                                │
│  • Извлечение face embeddings (InsightFace/ArcFace)                         │
│  • Определение ключевых черт лица                                            │
│  • Создание текстового описания лица для промпта                            │
│  • Определение лучшего ракурса и освещения                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     AGENT 2: Universe Researcher                             │
│  • Исследование вселенной фандома (Web Search + RAG)                        │
│  • Определение визуального стиля (рисованный/кинематографичный)             │
│  • Описание эстетики, цветовой палитры, атмосферы                           │
│  • Каталогизация ключевых персонажей                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      AGENT 3: Scene Architect                                │
│  • Генерация 10 культовых сцен из вселенной                                 │
│  • Разделение на категории: добро vs зло, эпик, драма                       │
│  • Подбор сцен под характеристики лица пользователя                         │
│  • Определение роли пользователя в каждой сцене                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      AGENT 4: Prompt Engineer                                │
│  • Создание детальных промптов для каждой сцены                             │
│  • Интеграция face description в промпт                                      │
│  • Добавление технических параметров (освещение, камера, стиль)             │
│  • Специфичные параметры для Niji/Midjourney                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       AGENT 5: Prompt Critic                                 │
│  • Анализ промптов на соответствие стилю фандома                            │
│  • Проверка нарративной логики (добро vs зло)                               │
│  • Оценка технических параметров (освещение, фотореализм)                   │
│  • Итеративное улучшение до score > 0.9                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    AGENT 6: Image Generator + Refiner                        │
│  • Генерация через Midjourney Niji Banania 3 Pro API                        │
│  • Face Swap постобработка (InsightFace inswapper)                          │
│  • Upscaling и улучшение качества                                            │
│  • Проверка сходства и регенерация при необходимости                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Ключевые техники для максимального сходства лица

### Вариант A: Face Swap Pipeline (Рекомендуется для Midjourney)
```
1. Генерация базового изображения в Midjourney/Niji
2. Face Swap с помощью InsightFace inswapper_128
3. Face Enhancement с GFPGAN/CodeFormer
4. Blending для естественности
```

### Вариант B: IP-Adapter + Stable Diffusion
```
1. Использование IP-Adapter Face ID
2. ControlNet для позы и композиции
3. LoRA для стиля фандома
4. Более глубокая интеграция лица в генерацию
```

### Вариант C: Hybrid (Лучшее качество)
```
1. Midjourney/Niji для базовой сцены (без лица)
2. Stable Diffusion + IP-Adapter для лица
3. Композитинг с помощью Segment Anything
4. Финальная гармонизация
```

---

## Структура проекта

```
fandom_generator/
├── __init__.py
├── main.py                          # Точка входа
├── config.py                        # Конфигурация API ключей
│
├── agents/
│   ├── __init__.py
│   ├── base.py                      # Базовый класс агента
│   ├── face_analyzer.py             # Агент анализа лица
│   ├── universe_researcher.py       # Агент исследования фандома
│   ├── scene_architect.py           # Агент создания сцен
│   ├── prompt_engineer.py           # Агент создания промптов
│   ├── prompt_critic.py             # Агент-критик
│   └── image_generator.py           # Агент генерации
│
├── face_processing/
│   ├── __init__.py
│   ├── embeddings.py                # Извлечение face embeddings
│   ├── analyzer.py                  # Анализ черт лица
│   ├── swapper.py                   # Face swap логика
│   └── enhancer.py                  # GFPGAN/CodeFormer
│
├── image_generation/
│   ├── __init__.py
│   ├── midjourney_client.py         # Клиент Midjourney API
│   ├── stable_diffusion.py          # SD + IP-Adapter
│   ├── compositor.py                # Композитинг изображений
│   └── upscaler.py                  # Улучшение разрешения
│
├── knowledge/
│   ├── __init__.py
│   ├── fandom_db.py                 # База знаний фандомов
│   ├── scene_templates.py           # Шаблоны сцен
│   └── style_guides.py              # Гайды по стилям
│
├── orchestrator/
│   ├── __init__.py
│   ├── pipeline.py                  # Основной пайплайн
│   └── quality_checker.py           # Проверка качества
│
├── api/
│   ├── __init__.py
│   └── web_app.py                   # Flask/FastAPI веб-интерфейс
│
└── utils/
    ├── __init__.py
    ├── image_utils.py               # Работа с изображениями
    └── prompt_utils.py              # Утилиты для промптов
```

---

## Этапы разработки

### Этап 1: Face Processing Core
**Цель:** Создать надежную систему анализа и обработки лиц

1. [ ] Интеграция InsightFace для извлечения embeddings
2. [ ] Создание Face Analyzer агента
3. [ ] Интеграция inswapper для face swap
4. [ ] Настройка GFPGAN/CodeFormer для улучшения лиц
5. [ ] Тестирование на разных типах лиц

### Этап 2: Universe Research Agent
**Цель:** Автоматическое исследование любого фандома

1. [ ] Интеграция с Claude API для исследования
2. [ ] Web search для актуальной информации
3. [ ] Классификация стиля (аниме/кино/комикс)
4. [ ] База данных популярных фандомов
5. [ ] Кэширование результатов исследования

### Этап 3: Scene & Prompt Agents
**Цель:** Создание качественных сцен и промптов

1. [ ] Scene Architect агент
2. [ ] Prompt Engineer агент
3. [ ] Prompt Critic агент с итеративным улучшением
4. [ ] Библиотека шаблонов для разных стилей
5. [ ] Специфичные оптимизации для Niji 3 Pro

### Этап 4: Image Generation Pipeline
**Цель:** Генерация с максимальным сходством

1. [ ] Клиент для Midjourney/Niji API
2. [ ] Интеграция face swap в пайплайн
3. [ ] Проверка сходства (face similarity score)
4. [ ] Автоматическая регенерация при низком score
5. [ ] Финальная постобработка

### Этап 5: Web Interface & API
**Цель:** Удобный интерфейс для пользователей

1. [ ] FastAPI backend
2. [ ] Веб-интерфейс для загрузки фото
3. [ ] Отображение прогресса генерации
4. [ ] Галерея результатов
5. [ ] Выбор сцен и настроек

---

## Техническая спецификация Face Swap Pipeline

### Критически важно для сходства:

```python
# Оптимальные параметры для InsightFace
FACE_SWAP_CONFIG = {
    "det_size": (640, 640),          # Размер детекции
    "det_thresh": 0.5,                # Порог детекции
    "similarity_threshold": 0.6,      # Мин. сходство для swap

    # Постобработка
    "use_gfpgan": True,
    "gfpgan_weight": 0.7,             # Баланс улучшения
    "use_codeformer": True,
    "codeformer_fidelity": 0.5,       # Точность к оригиналу

    # Blending
    "face_mask_blur": 10,             # Размытие маски
    "face_mask_erode": 5,             # Эрозия маски
}
```

### Face Similarity Scoring:
```python
# Проверка сходства после генерации
def check_similarity(original_face, generated_face):
    emb1 = face_analyzer.get_embedding(original_face)
    emb2 = face_analyzer.get_embedding(generated_face)
    similarity = np.dot(emb1, emb2)

    # Целевое значение > 0.75 для высокого сходства
    return similarity
```

---

## Промпт-инженерия для сохранения лица

### Техники для Midjourney/Niji:

1. **Character Reference (--cref)**
   ```
   [scene description] --cref [user_photo_url] --cw 100
   ```

2. **Детальное описание лица в промпте**
   ```
   "a person with [specific face features],
   [hair color/style], [eye color], [skin tone],
   [distinctive features like freckles/dimples]"
   ```

3. **Style Reference для стиля фандома**
   ```
   --sref [fandom_style_reference] --sw 50
   ```

4. **Комбинированный подход**
   ```
   [scene] featuring [face_description] --cref [photo] --cw 80
   --sref [style] --sw 40 --ar 16:9 --niji 6
   ```

---

## Зависимости

```txt
# Core
anthropic>=0.18.0
openai>=1.0.0
httpx>=0.25.0

# Face Processing
insightface>=0.7.3
onnxruntime-gpu>=1.16.0
opencv-python>=4.8.0
numpy>=1.24.0

# Image Enhancement
gfpgan>=1.3.8
basicsr>=1.4.2
facexlib>=0.3.0

# Image Generation
replicate>=0.22.0  # Для SD моделей
pillow>=10.0.0

# Web
fastapi>=0.109.0
uvicorn>=0.27.0
python-multipart>=0.0.6

# Utilities
aiohttp>=3.9.0
pydantic>=2.0.0
```

---

## API Integration Notes

### Midjourney через неофициальные API:
- midjourney-api (через Discord)
- Replicate hosted версии
- Собственный proxy через Discord бота

### Face Processing:
- InsightFace models: buffalo_l, inswapper_128
- Локальный inference или Replicate

---

## Метрики качества

| Метрика | Целевое значение |
|---------|------------------|
| Face Similarity Score | > 0.75 |
| Style Consistency | > 0.85 |
| Image Quality (BRISQUE) | < 30 |
| User Satisfaction | > 4.5/5 |

---

## Следующие шаги

1. **Начать с Этапа 1** - Face Processing Core
2. Создать базовую структуру проекта
3. Реализовать MVP с одним фандомом
4. Итеративно добавлять агентов
5. A/B тестирование разных подходов к face swap
