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

    def record_daily_deviation(
        self,
        date: str,
        planned_cal: float,
        target_cal: float,
        planned_p: float,
        target_p: float,
        cal_threshold: float = 0.15,
        p_threshold: float = 0.10
    ) -> dict:
        """Records or updates an idempotent daily deviation note in weekly.md.
        
        A diff is substantial if it deviates >= cal_threshold (default 15%) of Calories
        or >= p_threshold (default 10%) of Protein against daily target goals.
        If deviating, updates or creates exactly one entry for date.
        If within tolerance, clears any existing deviation entry for date.
        """
        cal_diff = int(round(planned_cal - target_cal))
        p_diff = int(round(planned_p - target_p))

        cal_pct = abs(planned_cal - target_cal) / target_cal if target_cal > 0 else 0.0
        p_pct = abs(planned_p - target_p) / target_p if target_p > 0 else 0.0

        is_deviating = (cal_pct >= cal_threshold) or (p_pct >= p_threshold)

        existing = self._read_notes(self.weekly_path, os.path.join(self.memory_dir, "weekly.json"))
        date_pattern = re.compile(rf"^\[?{re.escape(date)}\]?\s*Daily\s+deviation:", re.I)

        note_content = (
            f"[{date}] Daily deviation: {cal_diff:+d} kcal, {p_diff:+d}g P vs target "
            f"({int(round(planned_cal))} kcal / {int(round(planned_p))}g P planned vs "
            f"{int(round(target_cal))} kcal / {int(round(target_p))}g P target)"
        )

        filtered_notes = [n for n in existing if not date_pattern.search(n)]

        if is_deviating:
            filtered_notes.append(note_content)
            self._write_notes(self.weekly_path, filtered_notes)
            return {
                "status": "recorded",
                "deviating": True,
                "date": date,
                "cal_diff": cal_diff,
                "p_diff": p_diff,
                "note": note_content
            }
        else:
            if len(filtered_notes) != len(existing):
                self._write_notes(self.weekly_path, filtered_notes)
            return {
                "status": "cleared",
                "deviating": False,
                "date": date,
                "cal_diff": cal_diff,
                "p_diff": p_diff,
                "note": None
            }

    def rollover_weekly_memory(
        self,
        net_cal: float = 0.0,
        net_p: float = 0.0,
        daily_cal_target: float = 2500.0,
        daily_p_target: float = 150.0,
        cal_threshold: float = 0.15,
        p_threshold: float = 0.10,
        cycle_prefix: Optional[str] = None
    ) -> dict:
        """Rolls over short-term memory to a new week, carrying substantial net diffs.
        
        Clears previous week's short-term memory, and if the net difference is
        substantial (>= cal_threshold of daily calories or >= p_threshold of daily protein),
        writes a carried forward note into the fresh weekly.md.
        """
        self.clear_weekly_memory()

        cal_pct = abs(net_cal) / daily_cal_target if daily_cal_target > 0 else 0.0
        p_pct = abs(net_p) / daily_p_target if daily_p_target > 0 else 0.0

        is_substantial = (cal_pct >= cal_threshold) or (p_pct >= p_threshold)

        if is_substantial:
            c_int = int(round(net_cal))
            p_int = int(round(net_p))
            carried_note = f"[Carried from last week] Net weekly deviation: {c_int:+d} kcal, {p_int:+d}g P carried forward."
            self._write_notes(self.weekly_path, [carried_note])
            return {
                "carried": True,
                "note": carried_note,
                "net_cal": c_int,
                "net_p": p_int
            }

        if cycle_prefix:
            self._write_notes(self.weekly_path, [f"[Cycle {cycle_prefix}] Week initialized."])

        return {
            "carried": False,
            "note": None,
            "net_cal": int(round(net_cal)),
            "net_p": int(round(net_p))
        }

    def hydrate(self, user_timezone: str = "Europe/Brussels") -> tuple[list[tuple[str, str, float]], float]:
        """Loads only relevant context files (preferences, current week meal plan, memory) from disk, benchmarking latency."""
        from meal_planner.tools.artifacts import get_current_cycle_prefix
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
