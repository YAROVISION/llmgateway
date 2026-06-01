import os
import requests
from dotenv import load_dotenv

# Завантажуємо локальний .env для отримання ключа авторизації
load_dotenv()

BASE_URL = "https://llmgateway.lexis.blog"
API_KEY = os.getenv("GATEWAY_API_KEY", "change-me-to-a-strong-secret")

print(f"=== Тестування доступу до LLM Gateway на {BASE_URL} ===")

# 1. Тест healthcheck (HTTP -> HTTPS)
try:
    print(f"\n1. Перевірка редіректу http://llmgateway.lexis.blog/health...")
    r_http = requests.get("http://llmgateway.lexis.blog/health", allow_redirects=False, timeout=5)
    print(f"   HTTP Статус: {r_http.status_code}")
    if r_http.status_code in (301, 307, 308):
        print(f"   Успішно перенаправлено на: {r_http.headers.get('Location')}")
    else:
        print("   Увага: Немає редіректу!")
except Exception as e:
    print(f"   Помилка HTTP: {e}")

# 2. Тест HTTPS healthcheck (ігноруючи локальні помилки сертифікатів, якщо вони є)
try:
    print(f"\n2. Перевірка HTTPS Healthcheck: {BASE_URL}/health...")
    # verify=False на випадок застарілих локальних сертифікатів на розробницькій машині
    r_health = requests.get(f"{BASE_URL}/health", verify=False, timeout=10)
    print(f"   Статус: {r_health.status_code}")
    print(f"   Відповідь: {r_health.text}")
except Exception as e:
    print(f"   Помилка HTTPS Health: {e}")

# 3. Тест авторизації та генерації тексту (Chat Completions)
try:
    print(f"\n3. Перевірка Chat Completions ({BASE_URL}/v1/chat/completions)...")
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "auto",
        "messages": [{"role": "user", "content": "Привіт! Дай дуже коротку відповідь."}]
    }
    # verify=False для локального тесту
    r_chat = requests.post(f"{BASE_URL}/v1/chat/completions", json=payload, headers=headers, verify=False, timeout=15)
    print(f"   Статус: {r_chat.status_code}")
    if r_chat.status_code == 200:
        print(f"   Результат: {r_chat.json()['choices'][0]['message']['content']}")
    else:
        print(f"   Помилка авторизації або ротації: {r_chat.status_code} - {r_chat.text}")
except Exception as e:
    print(f"   Помилка Chat Completions: {e}")
