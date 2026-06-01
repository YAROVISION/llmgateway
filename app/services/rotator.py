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
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "..", "..", "scratch", "models_config.json")
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

        self.last_checked_date = ""
        self.providers: List[ProviderConfig] = self._build_providers()
        
        # Перевірка моделей при ініціалізації
        self.check_and_update_models()

    # ─── Побудова списку провайдерів ─────────────────────────────────────────

    def _load_models_config(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"⚠️  [Gateway] Failed to load models config: {e}")
        return {"last_checked_date": "", "models": {}}

    def _save_models_config(self, config: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(self.CONFIG_FILE), exist_ok=True)
            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️  [Gateway] Failed to save models config: {e}")

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

        config = self._load_models_config()
        self.last_checked_date = config.get("last_checked_date", "")
        models_dict = config.get("models", {})

        updated = False
        for name, _, _, default_model in entries:
            key = f"{name}::{default_model}"
            if key not in models_dict:
                models_dict[key] = default_model
                updated = True

        ollama_key = "ollama::qwen2.5-coder:14b"
        if ollama_key not in models_dict:
            models_dict[ollama_key] = "qwen2.5-coder:14b"
            updated = True

        if updated:
            config["models"] = models_dict
            self._save_models_config(config)

        providers = []
        for name, base_url, key_env, default_model in entries:
            current_model = models_dict.get(f"{name}::{default_model}", default_model)
            providers.append(ProviderConfig(name, base_url, os.getenv(key_env), current_model))

        ollama_model = models_dict.get(ollama_key, "qwen2.5-coder:14b")
        providers.append(ProviderConfig(
            name="ollama",
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model=ollama_model,
        ))

        return providers

    def check_and_update_models(self, force: bool = False) -> None:
        """
        Перевіряє актуальність моделей у провайдерів.
        Якщо модель недоступна, знаходить найкращу заміну та оновлює конфігурацію.
        """
        import datetime
        import difflib
        import httpx

        config = self._load_models_config()
        today = datetime.date.today().isoformat()

        if not force and config.get("last_checked_date") == today:
            print(f"ℹ️  [Gateway] Models check already done today ({today}). Skipping.")
            return

        print(f"🔎 [Gateway] Starting model relevance check ({today})...")

        cf_account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        env_mappings = {
            "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1"),
            "cerebras": ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1"),
            "sambanova": ("SAMBANOVA_API_KEY", "https://api.sambanova.ai/v1"),
            "nvidia": ("NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1"),
            "openrouter": ("OPENROUTERFORSKILLFORDIGEST", "https://openrouter.ai/api/v1"),
            "ollama": (None, "http://localhost:11434/v1"),
        }

        available_models: Dict[str, List[str]] = {}

        # 1. Fetch models for OpenAI-compatible providers
        for name, (key_env, base_url) in env_mappings.items():
            api_key = os.getenv(key_env) if key_env else "ollama"
            if name == "ollama" or api_key:
                try:
                    client = OpenAI(base_url=base_url, api_key=api_key)
                    models_list = client.models.list(timeout=10.0)
                    available_models[name] = [m.id for m in models_list.data]
                    print(f"  [Check] {name} has {len(available_models[name])} available models.")
                except Exception as e:
                    print(f"  ⚠️  [Check] Failed to list models for {name}: {e}")

        # 2. Fetch models for Cloudflare (custom search endpoint)
        cf_key = os.getenv("CLOUDFLARE_API_KEY")
        if cf_account and cf_key:
            try:
                url = f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/ai/models/search"
                headers = {"Authorization": f"Bearer {cf_key}"}
                response = httpx.get(url, headers=headers, timeout=10.0)
                data = response.json()
                if data.get("success"):
                    available_models["cloudflare"] = [
                        m.get("name") for m in data.get("result", []) if m.get("name")
                    ]
                    print(f"  [Check] cloudflare has {len(available_models['cloudflare'])} available models.")
                else:
                    print(f"  ⚠️  [Check] Cloudflare search API returned failure: {data.get('errors')}")
            except Exception as e:
                print(f"  ⚠️  [Check] Failed to list models for cloudflare: {e}")

        # Helper to find best replacement model
        def _get_best_replacement(missing: str, available: List[str]) -> str:
            if not available:
                return missing
            for a in available:
                if a.lower() == missing.lower():
                    return a
            matches = difflib.get_close_matches(missing, available, n=1, cutoff=0.3)
            if matches:
                return matches[0]
            missing_lower = missing.lower()
            for a in available:
                a_lower = a.lower()
                if "llama" in missing_lower and "llama" in a_lower:
                    return a
                if "qwen" in missing_lower and "qwen" in a_lower:
                    return a
                if "gpt" in missing_lower and "gpt" in a_lower:
                    return a
            return available[0]

        # 3. Verify each configured model and update if necessary
        models_dict = config.get("models", {})
        config_updated = False

        for key, current_model in list(models_dict.items()):
            provider_name = key.split("::")[0]
            if provider_name not in available_models:
                continue

            available_list = available_models[provider_name]
            if current_model not in available_list:
                replacement = _get_best_replacement(current_model, available_list)
                if replacement != current_model:
                    print(f"🔄 [Check] Model '{current_model}' is missing from {provider_name}. "
                          f"Updating to available model '{replacement}'")
                    models_dict[key] = replacement
                    config_updated = True

        config["last_checked_date"] = today
        config["models"] = models_dict
        self._save_models_config(config)
        self.last_checked_date = today

        # 4. If models were updated, rebuild the providers list in this instance
        if config_updated or force:
            self.providers = self._build_providers()
            print("✅ [Gateway] Providers reloaded with updated models.")
        else:
            print("✅ [Gateway] Models verification complete. No changes needed.")

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
        # Перевірка та оновлення моделей у фоновому режимі (якщо настала нова доба)
        import datetime
        today = datetime.date.today().isoformat()
        if getattr(self, "last_checked_date", "") != today:
            self.last_checked_date = today
            import threading
            threading.Thread(target=self.check_and_update_models, daemon=True).start()

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
