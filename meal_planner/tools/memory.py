from datetime import datetime
import json
import os
import re
import time
from typing import Optional

TRIVIAL_PATTERNS = [
    r"^(ok|okay|cool|great|sounds good|thanks|thank you|thx|hi|hello|hey|bye|goodbye)[!.]*$",
    r"^(yes|yeah|yep|sure|fine|no|nope|got it)[!.]*$"
]

class MemoryManager:
    """Manages short-term (weekly) and long-term (monthly/yearly) athlete memory."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.memory_dir = os.path.join(data_dir, "memory")
        os.makedirs(self.memory_dir, exist_ok=True)
        self.weekly_path = os.path.join(self.memory_dir, "weekly.json")
        self.long_term_path = os.path.join(self.memory_dir, "long_term.json")

    def is_trivial(self, note: str) -> bool:
        """Determines if a conversational note is trivial chatter and should not be stored."""
        cleaned = note.strip().lower()
        if len(cleaned) < 10:
            return True
        for pattern in TRIVIAL_PATTERNS:
            if re.match(pattern, cleaned):
                return True
        # Check if all tokens are conversational filler words
        tokens = re.findall(r"\b[a-zA-Z]+\b", cleaned)
        filler_words = {
            "ok", "okay", "cool", "great", "sounds", "good", "thanks", "thank", "you",
            "thx", "hi", "hello", "hey", "bye", "goodbye", "yes", "yeah", "yep",
            "sure", "fine", "no", "nope", "got", "it", "perfect", "awesome", "nice", "done"
        }
        if tokens and all(t in filler_words for t in tokens):
            return True
        return False

    def add_note(self, note: str, tier: str = "weekly") -> dict:
        """Adds a note to either short-term weekly or long-term memory with relevance filtering."""
        cleaned = note.strip()
        if self.is_trivial(cleaned):
            return {
                "status": "ignored",
                "reason": "Note recognized as trivial conversational chatter or too brief.",
                "note": cleaned
            }

        target_tier = "long_term" if tier in ["long_term", "long", "monthly", "yearly"] else "weekly"
        target_path = self.long_term_path if target_tier == "long_term" else self.weekly_path

        existing = []
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        # Deduplication check
        if any(item.get("note", "").lower() == cleaned.lower() for item in existing):
            return {
                "status": "ignored",
                "reason": "Duplicate note already stored in memory.",
                "tier": target_tier,
                "note": cleaned
            }

        entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "note": cleaned
        }
        existing.append(entry)

        # Cap weekly notes to 30 most recent to prevent bloat
        if target_tier == "weekly" and len(existing) > 30:
            existing = existing[-30:]

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

        return {
            "status": "saved",
            "tier": target_tier,
            "note": cleaned,
            "total_items": len(existing)
        }

    def get_context(self) -> dict:
        """Returns loaded memory for context injection."""
        weekly = []
        if os.path.exists(self.weekly_path):
            try:
                with open(self.weekly_path, "r", encoding="utf-8") as f:
                    weekly = json.load(f)
            except Exception:
                weekly = []

        long_term = []
        if os.path.exists(self.long_term_path):
            try:
                with open(self.long_term_path, "r", encoding="utf-8") as f:
                    long_term = json.load(f)
            except Exception:
                long_term = []

        return {
            "weekly": [item["note"] for item in weekly],
            "long_term": [item["note"] for item in long_term]
        }

    def clear_weekly_memory(self) -> None:
        """Clears short-term memory when rolling over to a new planning week."""
        if os.path.exists(self.weekly_path):
            with open(self.weekly_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def hydrate(self) -> tuple[list[tuple[str, str, float]], float]:
        """Loads all memory files from disk, benchmarking the latency for each."""
        targets = [
            ("Profile", os.path.join(self.data_dir, "profile.json")),
            ("Weekly Memory", self.weekly_path),
            ("Long-term Memory", self.long_term_path),
            ("Pantry Inventory", os.path.join(self.data_dir, "pantry.json"))
        ]

        # Also check for active meal plan CSV
        plans_dir = os.path.join(self.data_dir, "plans")
        if os.path.exists(plans_dir):
            csvs = sorted([f for f in os.listdir(plans_dir) if f.endswith("_meal_plan.csv")])
            if csvs:
                targets.append(("Active Weekly Plan", os.path.join(plans_dir, csvs[-1])))
        elif os.path.exists(os.path.join(self.data_dir, "meal_plan.csv")):
            targets.append(("Active Weekly Plan", os.path.join(self.data_dir, "meal_plan.csv")))

        records = []
        t_start_total = time.perf_counter()

        for label, path in targets:
            if os.path.exists(path):
                t0 = time.perf_counter()
                with open(path, "rb") as f:
                    _ = f.read()
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                records.append((label, path, round(elapsed_ms, 2)))

        total_ms = (time.perf_counter() - t_start_total) * 1000.0
        return records, round(total_ms, 2)


def add_memory_note(data_dir: str, note: str, tier: str = "weekly") -> dict:
    """Convenience function to add a memory note."""
    return MemoryManager(data_dir).add_note(note, tier)

def get_memory_context(data_dir: str) -> dict:
    """Convenience function to retrieve memory context."""
    return MemoryManager(data_dir).get_context()
