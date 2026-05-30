import os
import json
import time
from typing import Optional, List, Dict, Any
from openai import OpenAI
from dotenv import load_dotenv


class ProviderConfig:
    """Описує одного провайдера / модель."""
    def __init__(self, name: str, base_url: str, api_key: Optional[str], model: str,
                 extra_body: Optional[Dict] = None):
        self.name      = name
        self.base_url  = base_url
        self.api_key   = api_key
        self.model     = model
        self.extra_body = extra_body or {}

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "model": self.model, "base_url": self.base_url}


class LLMRotator:
    """
    Центральний сервіс ротації LLM-провайдерів.

    - Підтримує Groq, Cerebras, SambaNova, NVIDIA, Cloudflare, OpenRouter, Ollama.
    - Cooldown на рівні окремої моделі та цілого провайдера (rate-limit).
    - Preferred provider: через параметр, env PREFERRED_PROVIDER або scratch/agent_state.json.
    - OpenAI-сумісний інтерфейс — drop-in заміна.
    """

    FAILURES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "..", "scratch", "rotator_failures.json")
    COOLDOWN_SECONDS = 60

    def __init__(self):
        # Завантаження .env / .env.local (пошук вгору по дереву якщо не знайдено поряд)
        load_dotenv()
        load_dotenv(dotenv_path=".env.local", override=True)

        _env_keys = ["GROQ_API_KEY", "CEREBRAS_API_KEY", "SAMBANOVA_API_KEY",
                     "NVIDIA_API_KEY", "CLOUDFLARE_API_KEY", "OPENROUTERFORSKILLFORDIGEST"]
        if not any(os.getenv(k) for k in _env_keys):
            from dotenv import find_dotenv
            for fname in (".env", ".env.local"):
                p = find_dotenv(fname)
                if p:
                    load_dotenv(p, override=(fname == ".env.local"))

        self.providers: List[ProviderConfig] = self._build_providers()

    # ─── Побудова списку провайдерів ─────────────────────────────────────────

    def _build_providers(self) -> List[ProviderConfig]:
        cf_account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        entries = [
            # ── Groq ──────────────────────────────────────────────────────────
            ("groq",       "https://api.groq.com/openai/v1",
             "GROQ_API_KEY", "llama-3.3-70b-versatile"),
            ("groq",       "https://api.groq.com/openai/v1",
             "GROQ_API_KEY", "llama-3.1-8b-instant"),

            # ── Cerebras ──────────────────────────────────────────────────────
            ("cerebras",   "https://api.cerebras.ai/v1",
             "CEREBRAS_API_KEY", "llama3.1-8b"),
            ("cerebras",   "https://api.cerebras.ai/v1",
             "CEREBRAS_API_KEY", "qwen-3-235b-a22b-instruct-2507"),
            ("cerebras",   "https://api.cerebras.ai/v1",
             "CEREBRAS_API_KEY", "zai-glm-4.7"),

            # ── SambaNova ─────────────────────────────────────────────────────
            ("sambanova",  "https://api.sambanova.ai/v1",
             "SAMBANOVA_API_KEY", "Meta-Llama-3.3-70B-Instruct"),
            ("sambanova",  "https://api.sambanova.ai/v1",
             "SAMBANOVA_API_KEY", "DeepSeek-V3.1"),
            ("sambanova",  "https://api.sambanova.ai/v1",
             "SAMBANOVA_API_KEY", "Llama-4-Maverick-17B-128E-Instruct"),

            # ── NVIDIA ────────────────────────────────────────────────────────
            ("nvidia",     "https://integrate.api.nvidia.com/v1",
             "NVIDIA_API_KEY", "qwen/qwen3-coder-480b-a35b-instruct"),
            ("nvidia",     "https://integrate.api.nvidia.com/v1",
             "NVIDIA_API_KEY", "mistralai/mistral-large-3-675b-instruct-2512"),
            ("nvidia",     "https://integrate.api.nvidia.com/v1",
             "NVIDIA_API_KEY", "google/gemma-3n-e4b-it"),

            # ── Cloudflare ────────────────────────────────────────────────────
            ("cloudflare",
             f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/ai/v1",
             "CLOUDFLARE_API_KEY", "@cf/meta/llama-3.1-8b-instruct"),

            # ── OpenRouter ────────────────────────────────────────────────────
            ("openrouter", "https://openrouter.ai/api/v1",
             "OPENROUTERFORSKILLFORDIGEST", "poolside/laguna-m.1:free"),
            ("openrouter", "https://openrouter.ai/api/v1",
             "OPENROUTERFORSKILLFORDIGEST", "google/gemma-4-26b-a4b-it:free"),
            ("openrouter", "https://openrouter.ai/api/v1",
             "OPENROUTERFORSKILLFORDIGEST", "qwen/qwen3-next-80b-a3b-instruct:free"),
        ]

        providers = [
            ProviderConfig(name, base_url, os.getenv(key_env), model)
            for name, base_url, key_env, model in entries
        ]

        # Ollama — завжди доступний (локальний)
        providers.append(ProviderConfig(
            name="ollama",
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model="qwen2.5-coder:14b",
        ))

        return providers

    # ─── Публічний метод: список доступних провайдерів ───────────────────────

    def available_providers(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self.providers
                if p.api_key or p.name == "ollama"]

    # ─── Failures persistence ─────────────────────────────────────────────────

    def _load_failures(self) -> Dict[str, float]:
        try:
            if os.path.exists(self.FAILURES_FILE):
                with open(self.FAILURES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_failures(self, failures: Dict[str, float]) -> None:
        try:
            os.makedirs(os.path.dirname(self.FAILURES_FILE), exist_ok=True)
            with open(self.FAILURES_FILE, "w", encoding="utf-8") as f:
                json.dump(failures, f)
        except Exception:
            pass

    # ─── Preferred provider resolution ───────────────────────────────────────

    def _resolve_preferred(self, preferred_provider: Optional[str]) -> Optional[str]:
        """Повертає preferred_provider: параметр > env > agent_state.json."""
        if preferred_provider:
            return preferred_provider

        env_pref = os.getenv("PREFERRED_PROVIDER")
        if env_pref:
            return env_pref

        # Читаємо з agent_state.json (сумісність зі старими проектами)
        try:
            state_path = os.path.join(
                os.path.dirname(self.FAILURES_FILE), "agent_state.json"
            )
            if os.path.exists(state_path):
                with open(state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                model = state.get("model")
                api   = state.get("api_type")
                if model and model != "Автоматична ротація":
                    return model
                if api and api != "rotator":
                    return api
        except Exception:
            pass

        return None

    # ─── Головний метод ───────────────────────────────────────────────────────

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict] = None,
        preferred_provider: Optional[str] = None,
        model_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Спробує отримати відповідь від провайдерів по черзі.

        Повертає dict з полями:
            content        — текст відповіді
            provider_name  — назва провайдера (наприклад "groq")
            model          — модель, що відповіла
            duration       — час запиту в секундах
        """
        # Фільтр: тільки провайдери з ключем (або ollama)
        pool = [p for p in self.providers if p.api_key or p.name == "ollama"]
        print(f"🤖 [Gateway] Active providers: "
              f"{[p.name + '/' + p.model for p in pool]}")

        if not pool:
            raise RuntimeError("No LLM providers configured. Check your .env keys.")

        failures = self._load_failures()
        now = time.time()

        preferred = self._resolve_preferred(preferred_provider)

        # Якщо вказано конкретну модель — шукаємо її
        if model_hint and model_hint not in ("auto", ""):
            for p in pool:
                if p.model == model_hint or p.name == model_hint:
                    preferred = model_hint
                    break

        # Назва провайдера за preferred
        preferred_name: Optional[str] = None
        if preferred:
            for p in pool:
                if p.model == preferred:
                    preferred_name = p.name
                    break
            if not preferred_name:
                preferred_name = preferred  # може бути ім'ям провайдера

        def _sort_key(p: ProviderConfig) -> tuple:
            model_cd    = 1 if (now - failures.get(p.model, 0)) < self.COOLDOWN_SECONDS else 0
            provider_cd = 1 if (now - failures.get(f"provider::{p.name}", 0)) < self.COOLDOWN_SECONDS else 0
            is_cooldown = max(model_cd, provider_cd)
            if preferred:
                pref = 0 if p.model == preferred else (
                    1 if p.name == preferred_name else 2
                )
            else:
                pref = 2
            return (is_cooldown, pref)

        pool.sort(key=_sort_key)

        last_exc: Optional[Exception] = None

        for provider in pool:
            # Пропуск якщо cooldown ще активний
            if ((now - failures.get(f"provider::{provider.name}", 0)) < self.COOLDOWN_SECONDS or
                    (now - failures.get(provider.model, 0)) < self.COOLDOWN_SECONDS):
                print(f"⏭️  [Gateway] Skip {provider.name}/{provider.model} — cooldown active")
                continue

            try:
                print(f"🔄 [Gateway] Trying {provider.name} / {provider.model} ...")
                client = OpenAI(
                    base_url=provider.base_url,
                    api_key=provider.api_key,
                )

                params: Dict[str, Any] = {
                    "model":    provider.model,
                    "messages": messages,
                }
                if response_format:
                    params["response_format"] = response_format
                if provider.extra_body:
                    params["extra_body"] = provider.extra_body

                t0 = time.time()
                resp = client.chat.completions.create(timeout=15.0, **params)
                duration = time.time() - t0

                content = resp.choices[0].message.content
                print(f"✅ [Gateway] {provider.name}/{provider.model} responded in {duration:.2f}s")

                return {
                    "content":       content,
                    "provider_name": provider.name,
                    "model":         provider.model,
                    "duration":      round(duration, 3),
                }

            except Exception as exc:
                err = str(exc).lower()
                print(f"⚠️  [Gateway] {provider.name}/{provider.model} error: {exc}")

                # Блокуємо модель
                failures[provider.model] = now
                # Якщо rate-limit — блокуємо весь провайдер
                if any(x in err for x in ["rate limit", "429", "too many requests", "quota exceeded"]):
                    print(f"🚫 [Gateway] Rate-limit on provider {provider.name} — blocking whole provider")
                    failures[f"provider::{provider.name}"] = now

                self._save_failures(failures)
                last_exc = exc
                continue

        print("❌ [Gateway] All providers failed.")
        if last_exc:
            raise last_exc
        raise RuntimeError("All LLM providers failed.")
