# Meal Planner Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personalized, macro-accurate, zero-waste AI meal and grocery planner agent using Google's Agent Development Kit (ADK) / `agents-cli`, Gemini API, and local bookkeeping artifacts.

**Architecture:** An ADK-based agent architecture with deterministic calculation and catalog engines exposed as typed tools for profile onboarding, timezone anchoring, macro balancing, split grocery logistics (Saturday/Wednesday), zero-waste package allocation, and dynamic real-time schedule adaptation. All state is persisted locally in CSV and JSON artifacts.

**Tech Stack:** Python 3.13, Google ADK (`google-adk`), Google GenAI SDK (`google-genai`), `unittest` (standard library test runner), `zoneinfo` (standard library timezone support), `agents-cli`.

**Spec:** `docs/superpowers/specs/2026-10-10-meal-planner-agent-design.md`

## Global Constraints

- **Raw-Weight Precision:** All recipe outputs and macro calculations dictate dry/raw ingredient weights (e.g., 110g dry pho noodles, 200g raw lean beef), never cooked weights.
- **Texture Rules:** Breakfasts and dinners must strictly be soft, liquid, or broth-based; solid savory meals are strictly for lunches.
- **Food Safety & Fresh Meat Storage:** Fresh meat must never be stored in the fridge longer than 48–72 hours; grocery shopping is split into Saturday and Wednesday runs.
- **7-Day Planning Cycle:** The weekly schedule runs Saturday through Friday to align with the Saturday morning grocery run.
- **Zero-Waste Packaging:** Standard retail package quantities (e.g. 1kg frozen shrimp, 500g chicken breast) must be exhausted evenly across the week with zero perishable waste.
- **Timezone Awareness:** The agent prompts for the user's timezone on first initialization and anchors all conversational relative dates to the user's real-time clock.
- **Authentication:** Authenticates to Gemini via `GEMINI_API_KEY` from the environment or `.env` file.

## Review Focus

1. **Timezone Normalization Edge Cases:** Invalid or ambiguous timezone strings (e.g., `UTC+2`, `GMT-5`, misspelled `Europe/Brussles`) must cleanly fall back or prompt for valid IANA timezones instead of crashing `zoneinfo.ZoneInfo`.
2. **Macro Deficit / Surplus Feasibility:** Unrealistic macro targets (e.g. 3.0g P/kg on an aggressive 1500 kcal cut) must detect that remaining calories cannot satisfy carb/fat minimums and issue an informative warning rather than yielding negative carbohydrate grams.
3. **Rollover Meat Shelf-Life Expiry:** When rolling over unused fresh meat from a missed dinner (e.g. Thursday), if it cannot be consumed within 24 hours or before shelf-life limits, it must be explicitly flagged with `status: FREEZE` in logs and grocery trackers to prevent spoilage.
4. **Substitution Density Recalibration:** When substituting one protein source for another (e.g., chicken breast for pork shoulder due to price spikes), the raw weight must recalculate based on the substituted ingredient's specific protein density per 100g.
5. **Pantry Restock Boundary Condition:** Logging staple ingredient consumption (e.g., 30g ON Whey scoop from a 2.27kg tub) must decrement inventory accurately and trigger an item under the "Pantry Restock" section of `grocery_list.csv` only when stock crosses the reorder threshold.

---

### Task 1: Seed Catalog & Nutritional Models

**Files:**
- Create: `meal_planner/__init__.py`
- Create: `meal_planner/models.py`
- Create: `meal_planner/catalog/ingredients.json`
- Create: `meal_planner/catalog/recipes.json`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Consumes: None (foundational task)
- Produces:
  - `Ingredient(id: str, name: str, category: str, protein_per_100g: float, fat_per_100g: float, carbs_per_100g: float, calories_per_100g: float, package_size_g: float, unit_price_eur: float, perishable: bool)`
  - `Recipe(id: str, name: str, meal_type: str, texture: str, ingredients: list[dict], prep_type: str)`
  - `load_catalog(catalog_dir: str | None = None) -> tuple[dict[str, Ingredient], dict[str, Recipe]]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_catalog.py
import unittest
from meal_planner.models import load_catalog, Ingredient, Recipe

class TestCatalog(unittest.TestCase):
    def test_catalog_loads_ingredients_and_recipes(self):
        ingredients, recipes = load_catalog()
        self.assertIn("chicken_breast", ingredients)
        self.assertIn("pho_beef", recipes)
        
        # Check raw nutrient density
        chicken = ingredients["chicken_breast"]
        self.assertIsInstance(chicken, Ingredient)
        self.assertGreater(chicken.protein_per_100g, 20.0)
        self.assertTrue(chicken.perishable)

        # Check recipe texture rules
        pho = recipes["pho_beef"]
        self.assertIsInstance(pho, Recipe)
        self.assertEqual(pho.texture, "broth")
        self.assertEqual(pho.meal_type, "dinner")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_catalog.py`  
Expected: FAIL with `ModuleNotFoundError: No module named 'meal_planner'`

- [ ] **Step 3: Implement `models.py`, `catalog/ingredients.json`, `catalog/recipes.json`, and `load_catalog()`**

Create `meal_planner/__init__.py` and `meal_planner/models.py` with dataclasses and `load_catalog()`. Populate `ingredients.json` with Colruyt/Belgian staples: chicken breast, lean beef flank, pork shoulder, frozen black tiger shrimp (1000g), dry pho rice noodles, jasmine rice, Optimum Nutrition Gold Standard Whey (2270g), fortified soy milk (1000ml), Boni frozen avocado chunks (450g), eggs, fish sauce, lemongrass, scallions, fresh chili. Populate `recipes.json` with:
- Breakfast: `whey_soy_smoothie` (soft/liquid), `avocado_soy_shake` (soft/liquid).
- Lunch: `thit_kho_tau` (batch savory solid), `ga_xao_sa_ot` (batch savory solid).
- Dinner: `pho_bo_tai` (broth soft dinner), `pho_tom_noodle` (broth soft dinner).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_catalog.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/ tests/
git commit -m "feat(catalog): seed ingredients and recipes catalog with raw nutritional models"
```

---

### Task 2: Timezone Anchoring & Profile Onboarding Engine

**Files:**
- Create: `meal_planner/tools/onboarding.py`
- Test: `tests/test_onboarding.py`

**Interfaces:**
- Consumes: `meal_planner.models.UserProfile`
- Produces:
  - `resolve_timezone(tz_input: str) -> zoneinfo.ZoneInfo`
  - `get_relative_datetime(relative_expr: str, tz_name: str, reference_dt: datetime | None = None) -> tuple[datetime, str]`
  - `init_user_profile(data_dir: str, profile_data: dict) -> UserProfile`
  - `load_user_profile(data_dir: str) -> UserProfile | None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_onboarding.py
import unittest
from datetime import datetime
import zoneinfo
from meal_planner.tools.onboarding import resolve_timezone, get_relative_datetime

class TestOnboarding(unittest.TestCase):
    def test_resolve_valid_and_invalid_timezones(self):
        tz = resolve_timezone("Europe/Brussels")
        self.assertEqual(tz.key, "Europe/Brussels")
        # Review Focus 1: Timezone fallback
        fallback_tz = resolve_timezone("Invalid/Zone")
        self.assertEqual(fallback_tz.key, "UTC")

    def test_relative_date_anchoring(self):
        # Reference: Thursday 2026-10-15 14:00:00 Brussels time
        ref = datetime(2026, 10, 15, 14, 0, 0, tzinfo=zoneinfo.ZoneInfo("Europe/Brussels"))
        dt, meal_type = get_relative_datetime("tonight", "Europe/Brussels", reference_dt=ref)
        self.assertEqual(dt.strftime("%Y-%m-%d"), "2026-10-15")
        self.assertEqual(meal_type, "dinner")

        dt2, meal_type2 = get_relative_datetime("tomorrow's lunch", "Europe/Brussels", reference_dt=ref)
        self.assertEqual(dt2.strftime("%Y-%m-%d"), "2026-10-16")
        self.assertEqual(meal_type2, "lunch")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_onboarding.py`  
Expected: FAIL with `ModuleNotFoundError: No module named 'meal_planner.tools'`

- [ ] **Step 3: Implement `tools/onboarding.py`**

Implement `resolve_timezone` using `zoneinfo.ZoneInfo` with alias mappings (e.g. `UTC+2`, `CET`, `CEST`) and safe UTC fallback. Implement `get_relative_datetime` parsing expressions (`today`, `tonight`, `tomorrow's lunch`, `Thursday night`, `Saturday run`) relative to reference time. Implement JSON serialization for `UserProfile` in `data_dir/profile.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_onboarding.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/onboarding.py tests/test_onboarding.py
git commit -m "feat(onboarding): implement timezone anchoring and profile management"
```

---

### Task 3: Macro & Caloric Calculation Engine

**Files:**
- Create: `meal_planner/tools/macro_calculator.py`
- Test: `tests/test_macro_calculator.py`

**Interfaces:**
- Consumes: `UserProfile` from `meal_planner.models`
- Produces:
  - `MacroTargets(calories: float, protein_g: float, fat_g: float, carbs_g: float)`
  - `calculate_daily_targets(bodyweight_kg: float, protein_mult: float, fat_mult: float, target_calories: float) -> MacroTargets`
  - `solve_protein_raw_weight(required_protein_g: float, baseline_dish_protein_g: float, meat_protein_density: float) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_macro_calculator.py
import unittest
from meal_planner.tools.macro_calculator import calculate_daily_targets, solve_protein_raw_weight

class TestMacroCalculator(unittest.TestCase):
    def test_calculate_daily_targets_standard(self):
        # 65 kg, 2.3g/kg protein (= 149.5g), 1.0g/kg fat (= 65g), 2550 kcal target
        # Protein kcal = 149.5 * 4 = 598 kcal
        # Fat kcal = 65 * 9 = 585 kcal
        # Remaining kcal = 2550 - 598 - 585 = 1367 kcal -> Carbs = 1367 / 4 = 341.75g
        targets = calculate_daily_targets(65.0, 2.3, 1.0, 2550.0)
        self.assertAlmostEqual(targets.protein_g, 149.5, places=1)
        self.assertAlmostEqual(targets.fat_g, 65.0, places=1)
        self.assertAlmostEqual(targets.carbs_g, 341.75, places=1)

    def test_review_focus_macro_deficit_warning(self):
        # Review Focus 2: Target calories too low to sustain protein + fat minimums
        with self.assertRaises(ValueError):
            calculate_daily_targets(80.0, 3.0, 1.0, 1200.0)

    def test_solve_protein_raw_weight(self):
        # Needs 45g protein from chicken breast (density 23.5g per 100g), baseline dish has 5g protein
        # Net needed = 40g -> Raw weight = (40 / 23.5) * 100 = 170.21g
        weight = solve_protein_raw_weight(45.0, 5.0, 23.5)
        self.assertAlmostEqual(weight, 170.2, places=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_macro_calculator.py`  
Expected: FAIL with `ModuleNotFoundError: No module named 'meal_planner.tools.macro_calculator'`

- [ ] **Step 3: Implement `tools/macro_calculator.py`**

Implement `calculate_daily_targets` and `solve_protein_raw_weight`. Add validation asserting `target_calories >= (protein_kcal + fat_kcal + minimum_carb_floor)` to catch infeasible diets.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_macro_calculator.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/macro_calculator.py tests/test_macro_calculator.py
git commit -m "feat(macros): implement deterministic macro engine and raw-weight solver"
```

---

### Task 4: Zero-Waste 7-Day Meal Plan Generator & CSV Exporter

**Files:**
- Create: `meal_planner/tools/meal_generator.py`
- Test: `tests/test_meal_generator.py`

**Interfaces:**
- Consumes: `load_catalog()`, `calculate_daily_targets()`, `solve_protein_raw_weight()`
- Produces:
  - `generate_weekly_plan(profile: UserProfile) -> WeeklyPlan`
  - `export_meal_plan_csv(plan: WeeklyPlan, filepath: str) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_meal_generator.py
import unittest
import os
import csv
from meal_planner.models import UserProfile
from meal_planner.tools.meal_generator import generate_weekly_plan, export_meal_plan_csv

class TestMealGenerator(unittest.TestCase):
    def test_weekly_plan_texture_rules_and_package_exhaustion(self):
        profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )
        plan = generate_weekly_plan(profile)
        
        # Verify 7 days (Saturday to Friday)
        self.assertEqual(len(plan.days), 7)
        self.assertEqual(plan.days[0].day_name, "Saturday")
        self.assertEqual(plan.days[6].day_name, "Friday")

        # Texture rule verification
        for day in plan.days:
            self.assertIn(day.breakfast.texture, ["liquid", "soft"])
            self.assertEqual(day.lunch.texture, "solid")
            self.assertIn(day.dinner.texture, ["broth", "soft"])

        # Check raw weights in export
        csv_path = "tests/test_meal_plan.csv"
        export_meal_plan_csv(plan, csv_path)
        self.assertTrue(os.path.exists(csv_path))
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            self.assertEqual(len(rows), 21) # 7 days * 3 meals
            # Verify raw/dry specified in ingredients column
            self.assertTrue(any("raw" in r["Ingredients"].lower() or "dry" in r["Ingredients"].lower() for r in rows))
        os.remove(csv_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_meal_generator.py`  
Expected: FAIL with `ModuleNotFoundError: No module named 'meal_planner.tools.meal_generator'`

- [ ] **Step 3: Implement `tools/meal_generator.py`**

Implement `generate_weekly_plan` applying the Saturday–Friday cycle:
- Mon–Wed lunches scheduled as Sunday batch Thịt kho.
- Thu–Fri lunches scheduled as Wednesday batch Gà xào sả ớt.
- Sat & Sun lunches scheduled as fresh solid meals.
- Dinners scheduled as broth-based dishes (Phở bò, Phở tôm), distributing frozen shrimp package (1000g) evenly across 4 dinners (250g per dinner) to ensure zero waste.
- Implement `export_meal_plan_csv` writing UTF-8 CSV with columns: `Day, Date, Meal, Recipe, Ingredients, Raw_Weight_g, Protein_g, Fat_g, Carbs_g, Calories`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_meal_generator.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/meal_generator.py tests/test_meal_generator.py
git commit -m "feat(planner): implement zero-waste weekly meal planner and CSV export"
```

---

### Task 5: Split Grocery Logistics & Pantry Inventory Engine

**Files:**
- Create: `meal_planner/tools/grocery_planner.py`
- Test: `tests/test_grocery_planner.py`

**Interfaces:**
- Consumes: `WeeklyPlan` from `meal_planner.tools.meal_generator`, `load_catalog()`
- Produces:
  - `PantryState(items: dict[str, float])`
  - `SplitGroceryList(saturday_run: list[dict], wednesday_run: list[dict], pantry_restock: list[dict])`
  - `generate_split_groceries(plan: WeeklyPlan, pantry: PantryState) -> SplitGroceryList`
  - `export_grocery_list_csv(grocery_list: SplitGroceryList, filepath: str) -> None`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_grocery_planner.py
import unittest
import os
import csv
from meal_planner.models import UserProfile
from meal_planner.tools.meal_generator import generate_weekly_plan
from meal_planner.tools.grocery_planner import PantryState, generate_split_groceries, export_grocery_list_csv

class TestGroceryPlanner(unittest.TestCase):
    def test_split_grocery_runs_and_pantry_restock(self):
        profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )
        plan = generate_weekly_plan(profile)
        
        # Review Focus 5: Pantry threshold test
        # Pantry with plenty of rice (4000g), but low whey (150g, threshold 300g)
        pantry = PantryState(items={"jasmine_rice": 4000.0, "on_whey": 150.0, "cooking_oil": 800.0})
        
        groceries = generate_split_groceries(plan, pantry)
        
        # Saturday run must contain fresh meat for Sat-Tue only
        sat_names = [item["name"] for item in groceries.saturday_run]
        wed_names = [item["name"] for item in groceries.wednesday_run]
        restock_names = [item["name"] for item in groceries.pantry_restock]

        # Whey must be in restock, rice must NOT be restocked
        self.assertIn("Optimum Nutrition Gold Standard Whey (2.27kg)", restock_names)
        self.assertNotIn("Jasmine Rice (5kg)", restock_names)

        csv_path = "tests/test_groceries.csv"
        export_grocery_list_csv(groceries, csv_path)
        self.assertTrue(os.path.exists(csv_path))
        os.remove(csv_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_grocery_planner.py`  
Expected: FAIL with `ModuleNotFoundError: No module named 'meal_planner.tools.grocery_planner'`

- [ ] **Step 3: Implement `tools/grocery_planner.py`**

Implement `generate_split_groceries` dividing required ingredients into:
- `Saturday Run`: Ingredients for Sat & Sun meals, Sunday batch prep, and fresh meat for Sat–Tue (max 72h).
- `Wednesday Run`: Ingredients for Wednesday batch prep and fresh meat for Wed–Fri.
- `Pantry Restock`: Bulk items whose pantry inventory will fall below `reorder_threshold`.
Implement `export_grocery_list_csv` writing categorized CSV with columns: `Run, Item, Package_Size, Quantity, Estimated_Price_EUR, Storage_Type`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_grocery_planner.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/grocery_planner.py tests/test_grocery_planner.py
git commit -m "feat(groceries): implement split Saturday/Wednesday grocery engine and pantry tracking"
```

---

### Task 6: Bookkeeping, Price Tracking & Analytics

**Files:**
- Create: `meal_planner/tools/tracker.py`
- Test: `tests/test_tracker.py`

**Interfaces:**
- Consumes: Catalog, UserProfile
- Produces:
  - `init_bookkeeping_artifacts(data_dir: str) -> None`
  - `record_price(data_dir: str, item_id: str, store: str, price_eur: float, unit_type: str) -> None`
  - `log_meal_consumption(data_dir: str, entry: dict) -> None`
  - `get_analytics_summary(data_dir: str) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tracker.py
import unittest
import os
import shutil
from meal_planner.tools.tracker import init_bookkeeping_artifacts, record_price, log_meal_consumption, get_analytics_summary

class TestTracker(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/test_data"
        os.makedirs(self.test_dir, exist_ok=True)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_price_tracking_and_analytics(self):
        init_bookkeeping_artifacts(self.test_dir)
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "prices.csv")))
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "meal_logs.csv")))

        record_price(self.test_dir, "chicken_breast", "Colruyt", 9.50, "per_kg")
        log_meal_consumption(self.test_dir, {
            "date": "2026-10-10", "meal": "lunch", "recipe": "ga_xao_sa_ot",
            "adherence": "completed", "protein_cost_eur": 1.90, "calories": 650
        })

        summary = get_analytics_summary(self.test_dir)
        self.assertAlmostEqual(summary["total_protein_spend_eur"], 1.90)
        self.assertEqual(summary["logged_meals_count"], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_tracker.py`  
Expected: FAIL with `ModuleNotFoundError: No module named 'meal_planner.tools.tracker'`

- [ ] **Step 3: Implement `tools/tracker.py`**

Implement initialization of `prices.csv` (pre-seeded with baseline Colruyt unit prices), `meal_logs.csv`, and analytics aggregation functions.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_tracker.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/tracker.py tests/test_tracker.py
git commit -m "feat(tracker): implement price tracking, meal logging, and trend analytics"
```

---

### Task 7: Real-Time Dynamic Adaptation & Ingredient Rollover Engine

**Files:**
- Create: `meal_planner/tools/adaptation.py`
- Test: `tests/test_adaptation.py`

**Interfaces:**
- Consumes: `WeeklyPlan`, `MacroTargets`, `solve_protein_raw_weight()`
- Produces:
  - `apply_meal_deviation(plan: WeeklyPlan, deviation: dict) -> WeeklyPlan`
  - `apply_grocery_substitution(plan: WeeklyPlan, original_id: str, sub_id: str, new_price_eur: float) -> WeeklyPlan`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_adaptation.py
import unittest
from meal_planner.models import UserProfile
from meal_planner.tools.meal_generator import generate_weekly_plan
from meal_planner.tools.adaptation import apply_meal_deviation, apply_grocery_substitution

class TestAdaptation(unittest.TestCase):
    def test_thursday_missed_dinner_rollover_and_macro_adjustment(self):
        # Review Focus 3: Missed Thursday dinner rollover
        profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )
        plan = generate_weekly_plan(profile)
        
        # User drank a double shake instead of Thursday dinner
        updated_plan = apply_meal_deviation(plan, {
            "day": "Thursday",
            "meal": "dinner",
            "actual": "double_shake",
            "protein_consumed_g": 50.0,
            "calories_consumed": 300.0
        })

        # Thursday dinner marked as adapted
        thursday = next(d for d in updated_plan.days if d.day_name == "Thursday")
        self.assertEqual(thursday.dinner.recipe_name, "Double Whey Shake")
        
        # Unused meat flagged for rollover/freeze
        self.assertTrue(len(updated_plan.rollover_items) > 0)
        self.assertIn(updated_plan.rollover_items[0]["action"], ["rollover_to_friday", "freeze"])

    def test_substitution_density_recalculation(self):
        # Review Focus 4: Pork shoulder substituted by chicken breast
        profile = UserProfile(
            timezone="Europe/Brussels", bodyweight_kg=65.0,
            goal_state="lean_bulk", target_calories=2550.0,
            protein_multiplier=2.3, fat_multiplier=1.0
        )
        plan = generate_weekly_plan(profile)
        updated_plan = apply_grocery_substitution(plan, "pork_shoulder", "chicken_breast", 9.50)
        
        # Lunch with chicken must have adjusted raw weight reflecting chicken's higher protein density
        mon_lunch = next(d for d in updated_plan.days if d.day_name == "Monday").lunch
        self.assertIn("chicken", mon_lunch.recipe_name.lower())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_adaptation.py`  
Expected: FAIL with `ModuleNotFoundError: No module named 'meal_planner.tools.adaptation'`

- [ ] **Step 3: Implement `tools/adaptation.py`**

Implement deviation handler:
- Replaces planned meal with consumed alternative.
- Computes macro surplus/deficit and redistributes remaining protein into next day's broth dinner or smoothie without violating texture rules.
- Manages unused raw protein: checks remaining shelf-life (< 48h remaining until consumption -> rollover; otherwise flags `action: freeze`).
- Recalculates raw meat weights when substituting ingredients with different protein densities.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_adaptation.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/tools/adaptation.py tests/test_adaptation.py
git commit -m "feat(adaptation): implement dynamic deviation handling and ingredient rollover"
```

---

### Task 8: ADK Root Agent Integration & Terminal Runner

**Files:**
- Create: `meal_planner/agent.py`
- Create: `meal_planner/cli.py`
- Create: `main.py`
- Create: `pyproject.toml`
- Test: `tests/test_agent_tools.py`

**Interfaces:**
- Consumes: All tool modules (`onboarding`, `macro_calculator`, `meal_generator`, `grocery_planner`, `tracker`, `adaptation`)
- Produces:
  - `root_agent`: ADK Agent configured with Gemini instructions and typed tool bindings.
  - Interactive CLI runner in `cli.py` and `main.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_agent_tools.py
import unittest
from meal_planner.agent import get_agent_tools, build_system_instruction

class TestAgentTools(unittest.TestCase):
    def test_agent_tools_registered(self):
        tools = get_agent_tools()
        tool_names = [t.__name__ for t in tools]
        self.assertIn("tool_onboard_user", tool_names)
        self.assertIn("tool_generate_meal_plan", tool_names)
        self.assertIn("tool_report_meal_deviation", tool_names)
        self.assertIn("tool_substitute_ingredient", tool_names)
        self.assertIn("tool_get_analytics", tool_names)

    def test_system_instruction_contains_temporal_context(self):
        prompt = build_system_instruction("Europe/Brussels")
        self.assertIn("Europe/Brussels", prompt)
        self.assertIn("soft, liquid, or broth-based", prompt)
        self.assertIn("raw/dry ingredient weights", prompt)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_agent_tools.py`  
Expected: FAIL with `ModuleNotFoundError: No module named 'meal_planner.agent'`

- [ ] **Step 3: Implement `agent.py`, `cli.py`, `main.py`, and `pyproject.toml`**

Implement tool wrappers in `meal_planner/agent.py` exporting clean typed Python functions compatible with Gemini tool calling. Create `cli.py` with an interactive chat loop that loads `GEMINI_API_KEY`, initializes the ADK runner or fallback Google GenAI client, detects if `data/profile.json` exists to trigger onboarding, and prints responses. Provide `main.py` as top-level entry point.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_agent_tools.py`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add meal_planner/agent.py meal_planner/cli.py main.py pyproject.toml tests/test_agent_tools.py
git commit -m "feat(agent): assemble ADK root agent with Gemini tool calling and interactive CLI"
```

---

### Task 9: End-to-End Verification & Documentation

**Files:**
- Create: `README.md`
- Test: Run all unit tests across the entire test suite

**Interfaces:**
- Verifies all tasks against `meal-planner-requirements.md`

- [ ] **Step 1: Run full test suite to verify 100% test pass**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`  
Expected: All tests PASS with zero errors.

- [ ] **Step 2: Write comprehensive `README.md`**

Document:
- System overview and features.
- Installation: dependencies (`uv sync` or `pip install -e .`).
- Setup: setting `GEMINI_API_KEY`.
- Usage: running `python main.py` or `agents-cli run`.
- Artifact inspection: `data/meal_plan.csv`, `data/grocery_list.csv`, `data/prices.csv`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add comprehensive README with setup, requirements, and CLI instructions"
```
