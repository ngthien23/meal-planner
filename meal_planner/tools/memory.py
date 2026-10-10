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
    """Manages short-term (weekly) and long-term (monthly/yearly) athlete memory using Markdown text files."""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.memory_dir = os.path.join(data_dir, "memory")
        os.makedirs(self.memory_dir, exist_ok=True)
        self.weekly_path = os.path.join(self.memory_dir, "weekly.md")
        self.long_term_path = os.path.join(self.memory_dir, "long_term.md")

    def _read_notes(self, path: str, legacy_json_path: Optional[str] = None) -> list[str]:
        notes = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        if stripped.startswith("- ") or stripped.startswith("* "):
                            notes.append(stripped[2:].strip())
                        elif not stripped.startswith("#"):
                            notes.append(stripped)
            except Exception:
                pass
        elif legacy_json_path and os.path.exists(legacy_json_path):
            try:
                with open(legacy_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    notes = [item["note"] for item in data if isinstance(item, dict) and "note" in item]
            except Exception:
                pass
        return notes

    def _write_notes(self, path: str, notes: list[str]) -> None:
        lines = [f"- {n}\n" for n in notes]
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)

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
        legacy_json = os.path.join(self.memory_dir, f"{target_tier}.json")

        existing = self._read_notes(target_path, legacy_json)

        # Deduplication check
        if any(item.lower() == cleaned.lower() for item in existing):
            return {
                "status": "ignored",
                "reason": "Duplicate note already stored in memory.",
                "tier": target_tier,
                "note": cleaned
            }

        existing.append(cleaned)

        # Cap weekly notes to 30 most recent to prevent bloat
        if target_tier == "weekly" and len(existing) > 30:
            existing = existing[-30:]

        self._write_notes(target_path, existing)

        return {
            "status": "saved",
            "tier": target_tier,
            "note": cleaned,
            "total_items": len(existing)
        }

    def get_context(self) -> dict:
        """Returns loaded memory for context injection."""
        weekly = self._read_notes(self.weekly_path, os.path.join(self.memory_dir, "weekly.json"))
        long_term = self._read_notes(self.long_term_path, os.path.join(self.memory_dir, "long_term.json"))
        return {
            "weekly": weekly,
            "long_term": long_term
        }

    def clear_weekly_memory(self) -> None:
        """Clears short-term memory when rolling over to a new planning week."""
        if os.path.exists(self.weekly_path):
            with open(self.weekly_path, "w", encoding="utf-8") as f:
                f.write("")
        legacy = os.path.join(self.memory_dir, "weekly.json")
        if os.path.exists(legacy):
            try:
                os.remove(legacy)
            except Exception:
                pass

    def hydrate(self, user_timezone: str = "Europe/Brussels") -> tuple[list[tuple[str, str, float]], float]:
        """Loads only relevant context files (preferences, current week meal plan, memory) from disk, benchmarking latency."""
        from meal_planner.tools.meal_generator import get_current_cycle_prefix
        prefix = get_current_cycle_prefix(user_timezone)
        current_plan_csv = os.path.join(self.data_dir, "plans", f"{prefix}_meal_plan.csv")
        if not os.path.exists(current_plan_csv):
            root_plan = os.path.join(self.data_dir, "meal_plan.csv")
            if os.path.exists(root_plan):
                current_plan_csv = root_plan

        targets = [
            ("Current Week Meal Plan", current_plan_csv),
            ("Active Weekly Memory", self.weekly_path if os.path.exists(self.weekly_path) else os.path.join(self.memory_dir, "weekly.json")),
            ("Durable Long-term Facts", self.long_term_path if os.path.exists(self.long_term_path) else os.path.join(self.memory_dir, "long_term.json")),
        ]

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
