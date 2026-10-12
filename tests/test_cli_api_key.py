import unittest
import os
import shutil
import tempfile
from unittest.mock import patch
from meal_planner.cli import ensure_api_key

class TestCliApiKey(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.env_patcher = patch("meal_planner.cli.ENV_PATH", os.path.join(self.test_dir, ".env"))
        self.env_patcher.start()
        self.orig_key = os.environ.get("GEMINI_API_KEY")
        self.orig_google_key = os.environ.get("GOOGLE_API_KEY")
        self.orig_keys = os.environ.get("GEMINI_API_KEYS")
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]
        if "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]
        if "GEMINI_API_KEYS" in os.environ:
            del os.environ["GEMINI_API_KEYS"]

    def tearDown(self):
        self.env_patcher.stop()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if self.orig_key:
            os.environ["GEMINI_API_KEY"] = self.orig_key
        elif "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

        if self.orig_google_key:
            os.environ["GOOGLE_API_KEY"] = self.orig_google_key
        elif "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]

        if self.orig_keys:
            os.environ["GEMINI_API_KEYS"] = self.orig_keys
        elif "GEMINI_API_KEYS" in os.environ:
            del os.environ["GEMINI_API_KEYS"]

    def test_ensure_api_key_existing_env(self):
        os.environ["GEMINI_API_KEY"] = "test-existing-key"
        key = ensure_api_key(input_fn=lambda _: "should-not-be-called")
        self.assertEqual(key, "test-existing-key")

    def test_ensure_api_key_prompt_success(self):
        prompts = ["my-new-gemini-key", "n"]  # don't save to .env in test
        def mock_input(prompt=""):
            return prompts.pop(0)

        key = ensure_api_key(input_fn=mock_input)
        self.assertEqual(key, "my-new-gemini-key")
        self.assertEqual(os.environ.get("GEMINI_API_KEY"), "my-new-gemini-key")

    def test_ensure_api_key_prompt_skipped(self):
        key = ensure_api_key(input_fn=lambda _: "")
        self.assertEqual(key, "")
