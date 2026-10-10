import unittest
import os
from unittest.mock import patch
from meal_planner.cli import ensure_api_key

class TestCliApiKey(unittest.TestCase):
    def setUp(self):
        self.orig_key = os.environ.get("GEMINI_API_KEY")
        if "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

    def tearDown(self):
        if self.orig_key:
            os.environ["GEMINI_API_KEY"] = self.orig_key
        elif "GEMINI_API_KEY" in os.environ:
            del os.environ["GEMINI_API_KEY"]

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
