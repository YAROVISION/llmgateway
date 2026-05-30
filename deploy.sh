#!/bin/bash
# deploy.sh — деплой на Hostinger VPS (Ubuntu)
# Запускати на сервері: bash deploy.sh

set -e

echo "=== LLM Gateway Deploy ==="

# ── 1. Docker ─────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "→ Встановлення Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "⚠️  Перезайди в SSH-сесію і запусти deploy.sh ще раз (щоб група docker застосувалась)"
    exit 0
fi

if ! command -v docker &>/dev/null || ! docker compose version &>/dev/null 2>&1; then
    echo "→ Встановлення Docker Compose plugin..."
    sudo apt-get install -y docker-compose-plugin
fi

echo "✅ Docker $(docker --version)"

# ── 2. .env ────────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo ""
        echo "⚠️  Файл .env створено з шаблону."
        echo "    Відредагуй його перед запуском:"
        echo "    nano .env"
        echo ""
        echo "    Обов'язково встав:"
        echo "    GATEWAY_API_KEY=<сильний-секретний-ключ>"
        echo "    і ключі провайдерів (GROQ_API_KEY тощо)"
        echo ""
        read -p "Натисни Enter коли .env готовий, або Ctrl+C щоб вийти..."
    else
        echo "❌ Немає .env і .env.example. Поклади .env поряд зі скриптом."
        exit 1
    fi
fi

# ── 3. scratch dir ─────────────────────────────────────────────────────────────
mkdir -p scratch

# ── 4. Build & start ───────────────────────────────────────────────────────────
echo "→ Збірка і запуск контейнера..."
docker compose pull 2>/dev/null || true
docker compose up --build -d

echo ""
echo "→ Статус:"
docker compose ps

# ── 5. Nginx (опційно) ─────────────────────────────────────────────────────────
if command -v nginx &>/dev/null; then
    echo ""
    read -p "Налаштувати Nginx reverse proxy? (y/N) " setup_nginx
    if [[ "$setup_nginx" =~ ^[Yy]$ ]]; then
        read -p "Введи домен або IP: " domain
        sed "s/YOUR_DOMAIN/$domain/g" nginx.conf | sudo tee /etc/nginx/sites-available/llm-gateway > /dev/null
        sudo ln -sf /etc/nginx/sites-available/llm-gateway /etc/nginx/sites-enabled/llm-gateway
        sudo nginx -t && sudo systemctl reload nginx
        echo "✅ Nginx налаштовано для $domain"

        read -p "Встановити SSL через certbot? (y/N) " ssl
        if [[ "$ssl" =~ ^[Yy]$ ]]; then
            sudo apt-get install -y certbot python3-certbot-nginx
            sudo certbot --nginx -d "$domain"
        fi
    fi
fi

# ── 6. Health check ────────────────────────────────────────────────────────────
echo ""
echo "→ Перевірка health endpoint..."
sleep 3
if curl -sf http://localhost:8000/health > /dev/null; then
    echo "✅ Gateway запущено і відповідає"
    echo ""
    echo "📡 API: http://localhost:8000"
    echo "📖 Docs: http://localhost:8000/docs"
else
    echo "⚠️  Gateway не відповідає. Перевір логи:"
    echo "   docker compose logs -f"
fi
