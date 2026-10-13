import unittest
import os
import shutil
import tempfile
from unittest.mock import patch, AsyncMock, MagicMock

from meal_planner.key_manager import (
    KeyManager,
    get_api_keys,
    save_api_keys,
    is_retryable_api_error,
    RotatingKeyGemini,
)
from meal_planner.cli import ensure_api_key, quick_setup_wizard


class TestKeyManager(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_env = os.path.join(self.test_dir, ".env")
        self.orig_env = dict(os.environ)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)
        os.environ.pop("GEMINI_API_KEYS", None)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.environ.clear()
        os.environ.update(self.orig_env)

    def test_get_and_save_api_keys_round_trip(self):
        """save_api_keys persists multiple keys to .env and environment, and get_api_keys parses them."""
        keys = ["key-alpha", "key-beta", "key-gamma"]
        save_api_keys(keys, env_path=self.test_env)

        self.assertEqual(os.environ.get("GEMINI_API_KEYS"), "key-alpha,key-beta,key-gamma")
        self.assertEqual(os.environ.get("GEMINI_API_KEY"), "key-alpha")
        self.assertEqual(os.environ.get("GOOGLE_API_KEY"), "key-alpha")

        # Read back with clean env to test .env parsing
        os.environ.pop("GEMINI_API_KEYS", None)
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ.pop("GOOGLE_API_KEY", None)

        loaded = get_api_keys(env_path=self.test_env)
        self.assertEqual(loaded, ["key-alpha", "key-beta", "key-gamma"])

    def test_key_manager_round_robin_rotation(self):
        """KeyManager cycles through keys round-robin and updates os.environ on each rotation."""
        km = KeyManager(["key-1", "key-2", "key-3"])
        self.assertEqual(km.total_keys(), 3)
        self.assertTrue(km.has_multiple_keys())
        self.assertEqual(km.get_current_key(), "key-1")

        # Rotate to key-2
        next_k = km.rotate_key()
        self.assertEqual(next_k, "key-2")
        self.assertEqual(km.get_current_key(), "key-2")
        self.assertEqual(os.environ.get("GEMINI_API_KEY"), "key-2")
        self.assertEqual(os.environ.get("GOOGLE_API_KEY"), "key-2")

        # Rotate to key-3
        next_k = km.rotate_key()
        self.assertEqual(next_k, "key-3")
        self.assertEqual(km.get_current_key(), "key-3")

        # Wraps back to key-1
        next_k = km.rotate_key()
        self.assertEqual(next_k, "key-1")
        self.assertEqual(km.get_current_key(), "key-1")

    def test_is_retryable_api_error_patterns(self):
        """Validates detection of 429, Resource Exhausted, 400 Invalid Key, and non-retryable errors."""
        # 429 / Resource Exhausted
        class DummyError(Exception):
            def __init__(self, msg, code=None):
                super().__init__(msg)
                self.code = code

        self.assertTrue(is_retryable_api_error(DummyError("Resource Exhausted", 429)))
        self.assertTrue(is_retryable_api_error(Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded")))
        self.assertTrue(is_retryable_api_error(Exception("API_KEY_INVALID: 400 Bad Request")))
        self.assertTrue(is_retryable_api_error(Exception("503 Service Unavailable: The model is overloaded")))
        self.assertTrue(is_retryable_api_error(Exception("403 Quota exceeded for quota metric")))

        # Non-retryable
        self.assertFalse(is_retryable_api_error(ValueError("Invalid argument: foo")))
        self.assertFalse(is_retryable_api_error(KeyError("missing_key")))
        self.assertFalse(is_retryable_api_error(Exception("Syntax error in template")))

    def test_rotating_key_gemini_model_equality(self):
        """RotatingKeyGemini matches string model names for ADK compatibility."""
        model = RotatingKeyGemini(model="gemini-3.8-flash")
        self.assertEqual(model, "gemini-3.8-flash")
        self.assertEqual("gemini-3.8-flash", model)

    def test_ensure_api_key_multi_key_interactive(self):
        """ensure_api_key prompts for additional keys until an empty line is entered."""
        prompts = ["key-primary", "key-secondary", ""]
        def mock_input(prompt=""):
            return prompts.pop(0)

        with patch("meal_planner.cli.ENV_PATH", self.test_env):
            primary = ensure_api_key(input_fn=mock_input)

        self.assertEqual(primary, "key-primary")
        self.assertEqual(os.environ.get("GEMINI_API_KEYS"), "key-primary,key-secondary")
        self.assertEqual(os.environ.get("GEMINI_API_KEY"), "key-primary")

    def test_quick_setup_wizard_multi_key_comma_separated(self):
        """quick_setup_wizard handles comma-separated keys entered in a single prompt."""
        prompts = ["key-1, key-2, key-3", ""]
        def mock_input(prompt=""):
            return prompts.pop(0)

        with patch("meal_planner.cli.ENV_PATH", self.test_env):
            quick_setup_wizard(data_dir=self.test_dir, input_fn=mock_input, force=True)

        keys = get_api_keys(self.test_env)
        self.assertEqual(keys, ["key-1", "key-2", "key-3"])


class TestRotatingKeyGeminiExecution(unittest.IsolatedAsyncioTestCase):
    async def test_generate_content_async_rotates_and_retries_on_rate_limit(self):
        """generate_content_async catches rate-limit error, rotates key, and succeeds on next attempt."""
        km = KeyManager(["failing-key", "working-key"])
        model = RotatingKeyGemini(model="gemini-3.8-flash", key_mgr=km)

        call_count = 0

        async def fake_super_gen(req, stream=False):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt fails with 429
                raise Exception("429 RESOURCE_EXHAUSTED: Rate limit reached. Please try again.")
            # Second attempt succeeds
            yield "Success response token"

        from google.adk.models.llm_request import LlmRequest
        req = LlmRequest(model="gemini-3.8-flash")

        with patch("google.adk.models.google_llm.Gemini.generate_content_async", side_effect=fake_super_gen):
            responses = []
            async for resp in model.generate_content_async(req):
                responses.append(resp)

        self.assertEqual(call_count, 2)
        self.assertEqual(responses, ["Success response token"])
        self.assertEqual(km.get_current_key(), "working-key")

    async def test_generate_content_async_raises_when_all_keys_exhausted(self):
        """generate_content_async raises error if all keys in the pool fail."""
        km = KeyManager(["bad-key-1", "bad-key-2"])
        model = RotatingKeyGemini(model="gemini-3.8-flash", key_mgr=km)

        async def fake_always_fail(req, stream=False):
            raise Exception("429 RESOURCE_EXHAUSTED: Rate limit reached.")
            yield "never reached"

        from google.adk.models.llm_request import LlmRequest
        req = LlmRequest(model="gemini-3.8-flash")

        with patch("google.adk.models.google_llm.Gemini.generate_content_async", side_effect=fake_always_fail):
            with self.assertRaises(Exception) as ctx:
                async for _ in model.generate_content_async(req):
                    pass
            self.assertIn("RESOURCE_EXHAUSTED", str(ctx.exception))

    async def test_generate_content_async_switches_model_on_503_overload(self):
        """generate_content_async switches to fallback model and rotates key when 503 unavailable occurs."""
        km = KeyManager(["key-1", "key-2"])
        model = RotatingKeyGemini(model="gemini-3.8-flash", key_mgr=km)

        attempted_models = []

        async def fake_gen(req, stream=False):
            attempted_models.append(req.model)
            if len(attempted_models) == 1:
                # 503 high-demand error on primary model
                raise Exception("503 UNAVAILABLE. {'error': {'message': 'This model is currently experiencing high demand.'}}")
            # Fallback model succeeds
            yield f"Success from {req.model}"

        from google.adk.models.llm_request import LlmRequest
        req = LlmRequest(model="gemini-3.8-flash")

        with patch("google.adk.models.google_llm.Gemini.generate_content_async", side_effect=fake_gen):
            responses = []
            async for resp in model.generate_content_async(req):
                responses.append(resp)

        self.assertEqual(attempted_models[0], "gemini-3.8-flash")
        self.assertIn(attempted_models[1], ["gemini-3-flash-preview", "gemini-flash-latest"])
        self.assertIn("Success from", responses[0])
        self.assertEqual(km.get_current_key(), "key-2")


if __name__ == "__main__":
    unittest.main()
