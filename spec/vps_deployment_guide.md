# Інструкція з розгортання LLM Gateway на Hostinger VPS

Цей документ допоможе вам розгорнути та налаштувати сервіс автоматичної ротації безкоштовних моделей штучного інтелекту (LLM Gateway) на віртуальному сервері (VPS) від Hostinger.

Ми підготували два варіанти деплою:
1. **Варіант 1 (Ручний)**: Пряме копіювання файлів з комп'ютера через `rsync/scp`.
2. **Варіант 2 (Автоматичний через GitHub)**: CI/CD автоматизація за допомогою GitHub Actions при пуші коду.

---

## 🏗️ Структура проекту

Після об'єднання архівів проект має наступну готову структуру:
- [app/](file:///Users/kostantinkrivula/Desktop/sqlbase/rotator/app) — вихідний код додатку на FastAPI.
- [app/services/rotator.py](file:///Users/kostantinkrivula/Desktop/sqlbase/rotator/app/services/rotator.py) — сервіс ротації провайдерів (виправлено шлях до папки `scratch/`).
- [Dockerfile](file:///Users/kostantinkrivula/Desktop/sqlbase/rotator/Dockerfile) та [docker-compose.yml](file:///Users/kostantinkrivula/Desktop/sqlbase/rotator/docker-compose.yml) — конфігурація контейнеризації.
- [deploy.sh](file:///Users/kostantinkrivula/Desktop/sqlbase/rotator/deploy.sh) — автоматичний скрипт для встановлення Docker, збирання та запуску контейнера.
- [nginx.conf](file:///Users/kostantinkrivula/Desktop/sqlbase/rotator/nginx.conf) — налаштування зворотного проксі-сервера (reverse proxy) для Nginx.
- `.github/workflows/deploy.yml` — конфігурація автоматичного деплою для GitHub.

---

## 📋 Вимоги до сервера Hostinger

Для успішного запуску вам знадобиться:
1. **VPS тариф від Hostinger** (наприклад, KVM 1 або вище).
2. **Операційна система**: Ubuntu 22.04 LTS або 24.04 LTS (рекомендовано).
3. **Доменне ім'я** (опціонально, але необхідно для безкоштовного SSL-сертифікату від Let's Encrypt). Домен має бути спрямований на IP вашого VPS.

---

## 🚀 Варіант 1. Ручний деплой (пряме копіювання)

Цей варіант підходить, якщо ви хочете швидко запустити проект один раз без налаштування Git/GitHub.

### Крок 1. Підключення до сервера через SSH
```bash
ssh root@IP_ВАШОГО_СЕРВЕРА
```

### Крок 2. Копіювання файлів проекту на сервер
Запустіть цю команду **на локальному комп'ютері** з папки проекту:
```bash
# Створюємо папку на сервері
ssh root@IP_ВАШОГО_СЕРВЕРА "mkdir -p /root/llm-gateway"

# Копіюємо файли додатку
rsync -avz --exclude='venv' --exclude='.git' --exclude='__pycache__' --exclude='rotator_src' --exclude='rotatorhost_src' --exclude='*.zip' ./ root@IP_ВАШОГО_СЕРВЕРА:/root/llm-gateway/
```

### Крок 3. Налаштування файлу конфігурації `.env`
На сервері в папці `/root/llm-gateway`:
```bash
cp .env.example .env
nano .env
```
Вкажіть ваш `GATEWAY_API_KEY` та API-ключі провайдерів (Groq, Cerebras тощо).

### Крок 4. Запуск автоматичного деплою
```bash
bash deploy.sh
```
Дотримуйтесь інструкцій на екрані для конфігурації Nginx та SSL.

---

## 🐙 Варіант 2. Автоматичний деплой через GitHub Actions

Цей варіант дозволяє оновлювати програму на сервері автоматично щоразу, коли ви робите `git push` в репозиторій на GitHub.

### Крок 1. Ініціалізація Git локально та пуш на GitHub
Створіть **приватний** репозиторій на GitHub. Після цього виконайте команди у локальній папці проекту:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/ВАШ_НІК/НАЗВА_РЕПОЗИТОРІЮ.git
git push -u origin main
```

### Крок 2. Первинний клон на сервері Hostinger
Зайдіть на свій VPS через SSH та клонуйте створений репозиторій у папку `/root/llm-gateway`:
```bash
# Якщо GitHub вимагає авторизацію, краще налаштувати SSH-ключ на сервері для доступу до GitHub
git clone https://github.com/ВАШ_НІК/НАЗВА_РЕПОЗИТОРІЮ.git /root/llm-gateway
cd /root/llm-gateway
```

Створіть `.env` файл на сервері:
```bash
cp .env.example .env
nano .env
# Заповніть ваші API ключі
```

Запустіть первинне налаштування та Docker через deploy скрипт:
```bash
bash deploy.sh
```

### Крок 3. Налаштування SSH-ключів для GitHub Actions
Щоб GitHub міг підключитися до вашого VPS без пароля та оновити файли:

1. **Згенеруйте SSH-ключі** на своєму локальному комп'ютері або сервері:
   ```bash
   ssh-keygen -t rsa -b 4096 -f id_rsa_deploy -N ""
   ```
2. **Додайте публічний ключ** до списку дозволених на сервері:
   ```bash
   cat id_rsa_deploy.pub >> ~/.ssh/authorized_keys
   chmod 600 ~/.ssh/authorized_keys
   ```
3. **Скопіюйте приватний ключ** `id_rsa_deploy` (вміст файлу).

### Крок 4. Додавання секретів (Repository Secrets) на GitHub
Перейдіть до вашого репозиторію на GitHub:
**Settings ➔ Secrets and variables ➔ Actions ➔ New repository secret**

Створіть наступні секрети:
- `HOST` — IP-адреса вашого VPS від Hostinger.
- `USERNAME` — `root` (або інший користувач на сервері).
- `SSH_PRIVATE_KEY` — вставте вміст скопійованого файлу приватного ключа `id_rsa_deploy`.
- `PORT` — `22` (або інший порт SSH, якщо ви його змінювали).

### Як це працює:
Щоразу, коли ви будете робити `git push origin main` зі свого локального комп'ютера, GitHub Actions автоматично запустить робочий процес [deploy.yml](file:///Users/kostantinkrivula/Desktop/sqlbase/rotator/.github/workflows/deploy.yml). Він підключиться до VPS по SSH, виконає `git pull`, заново збере та перезапустить контейнери без простою сервісу.

---

## 📡 Використання сервісу

LLM Gateway повністю сумісний із клієнтськими SDK для OpenAI. Ви можете підключати його до будь-яких власних чат-ботів, скриптів чи веб-додатків.

### 🐍 Приклад на Python (openai SDK)
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://yourdomain.com/v1",  # Або http://IP:8000/v1
    api_key="your-gateway-key"            # GATEWAY_API_KEY з файлу .env
)

# Авторотація — шлюз сам вибере найкращий вільний провайдер та модель
response = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "Напиши вірш про космос"}]
)

print(response.choices[0].message.content)
```

### 💻 Перевірка стану (Health Check)
Ви можете дізнатися поточний стан шлюзу та які моделі/провайдери зараз доступні:
```bash
curl https://yourdomain.com/health
```
 Swagger-документація: `https://yourdomain.com/docs`
