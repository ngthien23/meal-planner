import os
import sys
import copy
import logging
from typing import Optional, AsyncGenerator

logger = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(REPO_ROOT, ".env")


def is_retryable_api_error(e: Exception) -> bool:
    """Returns True if the exception indicates rate limit, quota exhaustion, or an invalid/expired API key."""
    code = getattr(e, "code", None) or getattr(e, "status_code", None)
    if code in (400, 403, 429, 503):
        return True

    err_str = str(e).upper()
    retryable_patterns = [
        "429", "RESOURCE_EXHAUSTED", "RATE_LIMIT", "RATE LIMIT",
        "QUOTA", "EXHAUSTED", "TOO MANY REQUESTS",
        "400", "API_KEY_INVALID", "INVALID_ARGUMENT", "INVALID API KEY",
        "UNAUTHENTICATED", "PERMISSION_DENIED", "403",
        "503", "UNAVAILABLE", "OVERLOADED"
    ]
    return any(p in err_str for p in retryable_patterns)


def get_api_keys(env_path: Optional[str] = None) -> list[str]:
    """Retrieves all configured Gemini API keys from environment and .env file."""
    keys: list[str] = []

    # 1. Check environment variables
    multi_env = os.environ.get("GEMINI_API_KEYS", "").strip()
    if multi_env:
        for k in multi_env.split(","):
            k_clean = k.strip()
            if k_clean and k_clean not in keys:
                keys.append(k_clean)

    single_gemini = os.environ.get("GEMINI_API_KEY", "").strip()
    if single_gemini:
        for k in single_gemini.split(","):
            k_clean = k.strip()
            if k_clean and k_clean not in keys:
                keys.append(k_clean)

    single_google = os.environ.get("GOOGLE_API_KEY", "").strip()
    if single_google:
        for k in single_google.split(","):
            k_clean = k.strip()
            if k_clean and k_clean not in keys:
                keys.append(k_clean)

    # 2. Check .env file if path exists
    target_env = env_path if env_path is not None else getattr(sys.modules.get("meal_planner.cli"), "ENV_PATH", ENV_PATH)
    if os.path.exists(target_env):
        try:
            with open(target_env, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or not line:
                        continue
                    if line.startswith("GEMINI_API_KEYS="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        for k in val.split(","):
                            k_clean = k.strip()
                            if k_clean and k_clean not in keys:
                                keys.append(k_clean)
                    elif line.startswith("GEMINI_API_KEY=") or line.startswith("GOOGLE_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        for k in val.split(","):
                            k_clean = k.strip()
                            if k_clean and k_clean not in keys:
                                keys.append(k_clean)
        except Exception:
            pass

    return keys


def save_api_keys(keys: list[str], env_path: Optional[str] = None) -> None:
    """Persists multiple API keys to the .env file and process environment."""
    clean_keys: list[str] = []
    for k in keys:
        if isinstance(k, str):
            for sub in k.split(","):
                sub_clean = sub.strip()
                if sub_clean and sub_clean not in clean_keys:
                    clean_keys.append(sub_clean)
    if not clean_keys:
        return

    joined = ",".join(clean_keys)
    primary = clean_keys[0]

    os.environ["GEMINI_API_KEYS"] = joined
    os.environ["GEMINI_API_KEY"] = primary
    os.environ["GOOGLE_API_KEY"] = primary

    key_manager.set_keys(clean_keys)

    target_env = env_path if env_path is not None else getattr(sys.modules.get("meal_planner.cli"), "ENV_PATH", ENV_PATH)
    lines: list[str] = []
    if os.path.exists(target_env):
        try:
            with open(target_env, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            lines = []

    new_lines: list[str] = []
    found_keys = False
    found_gemini = False
    found_google = False

    for line in lines:
        if line.startswith("GEMINI_API_KEYS="):
            new_lines.append(f"GEMINI_API_KEYS={joined}\n")
            found_keys = True
        elif line.startswith("GEMINI_API_KEY="):
            new_lines.append(f"GEMINI_API_KEY={primary}\n")
            found_gemini = True
        elif line.startswith("GOOGLE_API_KEY="):
            new_lines.append(f"GOOGLE_API_KEY={primary}\n")
            found_google = True
        else:
            new_lines.append(line)

    if not found_keys:
        new_lines.append(f"GEMINI_API_KEYS={joined}\n")
    if not found_gemini:
        new_lines.append(f"GEMINI_API_KEY={primary}\n")
    if not found_google:
        new_lines.append(f"GOOGLE_API_KEY={primary}\n")

    os.makedirs(os.path.dirname(os.path.abspath(target_env)), exist_ok=True)
    with open(target_env, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


class KeyManager:
    """Manages an in-memory pool of Gemini API keys with automatic round-robin rotation on failures."""

    def __init__(self, keys: Optional[list[str]] = None):
        self.keys: list[str] = [k.strip() for k in keys if k and k.strip()] if keys else []
        self.current_index: int = 0

    def reload(self, env_path: Optional[str] = None) -> list[str]:
        """Reloads keys from environment and .env file."""
        self.keys = get_api_keys(env_path)
        self.current_index = 0
        return self.keys

    def set_keys(self, keys: list[str]) -> None:
        """Sets the keys pool."""
        self.keys = [k.strip() for k in keys if k and k.strip()]
        self.current_index = 0

    def get_current_key(self) -> Optional[str]:
        """Returns the currently active API key, or None if no keys configured."""
        if not self.keys:
            return None
        return self.keys[self.current_index % len(self.keys)]

    def rotate_key(self) -> Optional[str]:
        """Rotates to the next API key in the pool and updates process environment."""
        if not self.keys:
            return None
        self.current_index = (self.current_index + 1) % len(self.keys)
        new_key = self.keys[self.current_index]
        os.environ["GEMINI_API_KEY"] = new_key
        os.environ["GOOGLE_API_KEY"] = new_key
        return new_key

    def total_keys(self) -> int:
        """Returns the total number of configured keys."""
        return len(self.keys)

    def has_multiple_keys(self) -> bool:
        """Returns True if more than 1 key is configured."""
        return len(self.keys) > 1

    def get_keys(self) -> list[str]:
        """Returns a copy of the keys list."""
        return list(self.keys)


key_manager = KeyManager(get_api_keys())


# ==============================================================================
# Google ADK Rotating Model Subclass
# ==============================================================================
try:
    from google.adk.models.google_llm import Gemini
    from google.adk.models.llm_request import LlmRequest
    from google.adk.models.llm_response import LlmResponse
    import contextlib

    class RotatingKeyGemini(Gemini):
        """ADK Gemini model wrapper that automatically rotates through API keys upon rate limits or errors."""

        key_mgr: KeyManager = key_manager

        def __init__(self, **data):
            super().__init__(**data)
            self._set_active_key(self.key_mgr.get_current_key())

        def __eq__(self, other):
            if isinstance(other, str):
                return self.model == other
            return super().__eq__(other)

        def _set_active_key(self, key: Optional[str]) -> None:
            if not key:
                return
            os.environ["GEMINI_API_KEY"] = key
            os.environ["GOOGLE_API_KEY"] = key
            try:
                from google.genai import Client
                self.client = Client(api_key=key)
            except Exception:
                pass
            if hasattr(self, "_per_loop_api_client"):
                try:
                    delattr(self, "_per_loop_api_client")
                except AttributeError:
                    pass
            if hasattr(self, "_per_loop__live_api_client"):
                try:
                    delattr(self, "_per_loop__live_api_client")
                except AttributeError:
                    pass

        async def generate_content_async(
            self, llm_request: LlmRequest, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            max_attempts = max(1, self.key_mgr.total_keys())
            attempts = 0

            while attempts < max_attempts:
                curr_key = self.key_mgr.get_current_key()
                self._set_active_key(curr_key)
                yielded_any = False
                req_copy = (
                    llm_request.model_copy(deep=True)
                    if hasattr(llm_request, "model_copy")
                    else copy.deepcopy(llm_request)
                )
                try:
                    async for resp in super().generate_content_async(req_copy, stream=stream):
                        yielded_any = True
                        yield resp
                    return
                except Exception as e:
                    if not is_retryable_api_error(e) or attempts >= max_attempts - 1 or yielded_any:
                        raise e

                    attempts += 1
                    next_key = self.key_mgr.rotate_key()
                    logger.warning(
                        f"[KeyManager] API error ({type(e).__name__}: {e}). "
                        f"Rotating to API key {attempts + 1}/{max_attempts} and retrying turn..."
                    )
                    print(
                        f"\n[KeyManager] Rate limit or API error ({e}). "
                        f"Rotating to key {attempts + 1}/{max_attempts} and retrying in the same session...\n"
                    )

        @contextlib.asynccontextmanager
        async def connect(self, llm_request: LlmRequest):
            max_attempts = max(1, self.key_mgr.total_keys())
            attempts = 0
            while attempts < max_attempts:
                curr_key = self.key_mgr.get_current_key()
                self._set_active_key(curr_key)
                req_copy = (
                    llm_request.model_copy(deep=True)
                    if hasattr(llm_request, "model_copy")
                    else copy.deepcopy(llm_request)
                )
                try:
                    async with super().connect(req_copy) as conn:
                        yield conn
                    return
                except Exception as e:
                    if not is_retryable_api_error(e) or attempts >= max_attempts - 1:
                        raise e
                    attempts += 1
                    self.key_mgr.rotate_key()

except ImportError:
    class RotatingKeyGemini:
        pass
