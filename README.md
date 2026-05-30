# LLM Gateway

Локальний OpenAI-сумісний API-сервер з автоматичною ротацією LLM-провайдерів.  
Запускаєш один раз — підключаєш до будь-якого проекту як звичайний OpenAI клієнт.

---

## Швидкий старт

```bash
# 1. Встановлення залежностей
pip install -r requirements.txt

# 2. Налаштування
cp .env.example .env
# відредагуй .env: встав GATEWAY_API_KEY та ключі провайдерів

# 3. Запуск
python -m app.main
# або
uvicorn app.main:app --reload
```

Документація: http://localhost:8000/docs

---

## Підключення з будь-якого проекту

### Python (openai SDK — drop-in заміна)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="your-gateway-key"   # GATEWAY_API_KEY з .env
)

# Авторотація — gateway сам обирає найкращий вільний провайдер
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Привіт!"}]
)
print(response.choices[0].message.content)
```

### Python — вибір конкретного провайдера

```python
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Напиши код на Python"}],
    extra_body={"preferred_provider": "groq"}
)
```

### curl

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer your-gateway-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"Hello!"}]}'
```

### JavaScript / Node.js

```js
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8000/v1",
  apiKey: "your-gateway-key",
});

const res = await client.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "Hello!" }],
});
console.log(res.choices[0].message.content);
```

---

## Корисні ендпоінти

| Метод | URL | Опис |
|-------|-----|------|
| `GET` | `/health` | Стан сервісу, список провайдерів (без авторизації) |
| `GET` | `/v1/models` | Список всіх доступних моделей |
| `POST` | `/v1/chat/completions` | Основний ендпоінт (OpenAI-compatible) |
| `GET` | `/docs` | Swagger UI |

---

## Налаштування провайдерів

Додай ключі в `.env`. Gateway автоматично виключає провайдерів без ключів.

| Провайдер | Env змінна | Безкоштовний ліміт |
|-----------|-----------|---------------------|
| Groq | `GROQ_API_KEY` | ✅ Щедрий free tier |
| Cerebras | `CEREBRAS_API_KEY` | ✅ Free tier |
| SambaNova | `SAMBANOVA_API_KEY` | ✅ Free tier |
| NVIDIA | `NVIDIA_API_KEY` | ✅ Free credits |
| Cloudflare AI | `CLOUDFLARE_API_KEY` + `CLOUDFLARE_ACCOUNT_ID` | ✅ Free tier |
| OpenRouter | `OPENROUTERFORSKILLFORDIGEST` | ✅ Free моделі |
| Ollama | — (localhost) | ✅ Локальний |

---

## Логіка ротації

1. Провайдери без ключів виключаються.
2. Якщо вказано `preferred_provider` — він іде першим.
3. Якщо провайдер повернув помилку — модель блокується на 60 секунд.
4. Якщо помилка `429 / rate limit` — блокується весь провайдер на 60 секунд.
5. Стан зберігається у `scratch/rotator_failures.json`.

---

## Структура проекту

```
llm-gateway/
├── app/
│   ├── main.py              # FastAPI app + auth middleware
│   ├── models.py            # Pydantic schemas (OpenAI-compatible)
│   ├── routes/
│   │   ├── chat.py          # POST /v1/chat/completions
│   │   ├── models.py        # GET /v1/models
│   │   └── health.py        # GET /health
│   └── services/
│       └── rotator.py       # Логіка ротації провайдерів
├── scratch/                 # Runtime: failures.json, agent_state.json
├── .env.example
├── requirements.txt
└── README.md
```
