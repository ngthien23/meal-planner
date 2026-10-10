# Meal Planner Agent Design Specification

**Date:** 2026-10-10  
**Status:** Approved & Finalized for Implementation Planning

---

## 1. Intent & The Why

Athletes and powerlifters face significant cognitive overhead when balancing macro accuracy, chewing fatigue, grocery shelf life, and food waste against real-life schedule disruptions. Existing meal planning apps assume rigid schedules, cooked weights, or generic recipes that fail to accommodate specialized texture needs (e.g., liquid/broth dinners to avoid chewing fatigue) and perishable grocery logistics.

This project creates an AI-driven Meal & Grocery Planner Agent built with Google's **Agent Development Kit (ADK)** and managed via **`agents-cli`**, powered by Gemini with a `GEMINI_API_KEY`. It maintains persistent bookkeeping artifacts (CSV/JSON), anchors conversation in the user's local timezone, and enables conversational, real-time plan adjustments.

---

## 2. Goals, Non-Goals, & Anti-Goals

### Goals
- **Interactive Onboarding:** On first run (when no user profile exists), the agent conducts an onboarding conversation collecting:
  - Timezone (e.g., `Europe/Brussels`, `America/New_York`, `UTC+2`).
  - Current bodyweight (kg) & goal state (lean bulk, cut, maintenance).
  - Target daily calories (or TDEE multiplier).
  - Protein & fat multipliers (e.g., 2.3g P/kg, 1.0g F/kg, remaining to carbs).
  - Ingredient restrictions (no dairy milk, ON whey only, canned tuna only).
  - Texture rules (liquid/broth/soft breakfasts & dinners, solid savory lunches).
  - Batch cooking days (Sunday evening, Wednesday evening).
- **Timezone & Temporal Anchoring:** Store user's timezone; anchor all conversational time references ("tonight", "tomorrow's lunch", "Thursday dinner") to the user's real-time clock.
- **Dynamic Macro Engine:** Deterministic calculation of daily targets:
  - Calories, Protein, Fat, Carbohydrates.
  - Carbs and fats fixed flat across all 7 days.
  - Protein target satisfied by dynamically adjusting raw weights of scheduled protein sources (chicken breast, lean beef, pork, shrimp).
- **Raw-Weight Precision & Zero-Waste Meal Plans:** Output all ingredient quantities in raw/dry weights (e.g., 110g dry pho rice noodles, 200g raw lean beef). Plan batch meals around whole package sizes (e.g., exactly 1kg frozen shrimp across 4 dinners) to eliminate perishable waste.
- **Split Grocery Logistics (Saturday–Friday Cycle):**
  - The 7-day planning cycle runs **Saturday through Friday** to match the Saturday grocery run.
  - **Saturday Run:** Ingredients for Sat/Sun fresh meals + Sunday batch prep (Mon–Wed lunches) + Sat/Sun/Mon/Tue fresh meats (meat never stored in fridge > 72h).
  - **Wednesday Run:** Ingredients for Wednesday batch prep (Thu–Fri lunches) + Wed/Thu/Fri fresh meats.
- **Pantry & Bulk Staples Management:** Separate weekly perishable shopping from bulk staples (2.27kg ON whey tub, 5kg rice bags, soy milk cartons, cooking oil) via `data/pantry.json`, restocking only when running low so weekly spend isn't inflated.
- **Local Bookkeeping Artifacts:** Read/write structured local files:
  - `data/profile.json`: User profile, macros, restrictions, and timezone.
  - `data/pantry.json`: Stock levels and reorder thresholds for bulk staples.
  - `data/meal_plan.csv`: Current week's meal schedule with day, meal type, recipe name, raw ingredients, and macros.
  - `data/grocery_list.csv`: Itemized shopping list split by shopping run (Saturday Run vs. Wednesday Run) and Pantry Restock.
  - `data/prices.csv`: Unit price tracking for staple ingredients.
  - `data/meal_logs.csv`: Historical log of consumed meals and deviations.
- **Dynamic Real-Time Adaptation:** Re-plan upcoming meals when user logs deviations (e.g. skipped dinner, drank a double shake, or bought extra chicken because pork shoulder was overpriced), rolling over perishable ingredients to avoid spoilage.
- **ADK / agents-cli Compatibility:** Built using Google ADK (`google-adk`) agent architecture, executable locally via `agents-cli playground` or terminal CLI runner.

### Non-Goals
- Automated grocery checkout / web scraping of live supermarket inventory.
- Complex GUI or mobile app (focus is terminal/playground and local CSV inspection).
- Multi-user authentication / cloud multi-tenancy in phase 1 (single-user local workspace).

### Anti-Goals
- **No cooked-weight guidance:** Never output post-cook weights; all macro tracking relies on dry/raw ingredient measurements.
- **No solid/chewy dinners or breakfasts:** Never violate texture rules (breakfast and dinner must be soft/liquid/broth-based; solid savory meals are strictly for lunch).
- **No fresh meat storage > 72 hours:** Never schedule a single weekly grocery run for perishable meats without freezer designation.
- **No unexhausted perishable package fragments:** Never leave partial packages of perishable ingredients stranded without scheduled consumption.

---

## 3. Constraints

- **Python Environment:** Python 3.10+ (current environment is Python 3.13).
- **Tooling & Framework:** Google `agents-cli` and `google-adk` Python framework.
- **LLM & Credentials:** Gemini model (e.g., `gemini-2.5-flash` or `gemini-2.0-flash`), authenticated via `GEMINI_API_KEY`.
- **Operating System:** Windows compatible (handles Windows paths and UTF-8 CSV encoding).
- **Data Persistence:** Local flat files (`data/` directory) for immediate human readability in spreadsheet viewers.

---

## 4. Architecture & Key Modules

```
meal_planner/
├── __init__.py
├── agent.py                 # ADK Root Agent definition with instructions & tools
├── catalog/                 # Seed data for recipes & ingredient nutritional profiles
│   ├── ingredients.json     # Raw nutritional densities (P/F/C/kcal per 100g), unit prices, package sizes
│   └── recipes.json         # Base recipes categorized by meal slot (soft breakfast, batch lunch, broth dinner)
├── tools/
│   ├── __init__.py
│   ├── onboarding.py        # Profile & timezone management
│   ├── macro_calculator.py  # Macro calculation & protein raw-weight adjustments
│   ├── meal_generator.py    # Zero-waste meal planning & CSV generation
│   ├── grocery_planner.py   # Split Saturday/Wednesday shopping run logic & pantry checks
│   ├── tracker.py           # Price tracking, meal logging, and trend queries
│   └── adaptation.py        # Real-time deviation handler & ingredient roll-over
├── data/                    # Local bookkeeping artifacts (CSV/JSON)
│   ├── profile.json
│   ├── pantry.json
│   ├── meal_plan.csv
│   ├── grocery_list.csv
│   ├── prices.csv
│   └── meal_logs.csv
└── tests/                   # Test suite
    ├── test_macro_calculator.py
    ├── test_zero_waste.py
    ├── test_split_groceries.py
    └── test_adaptation.py
```

### Module 1: Profile & Preference Management (`tools/onboarding.py`)
- First-run wizard prompts for:
  - Timezone (validated against `zoneinfo`).
  - Bodyweight (kg) & Goal state (lean bulk, cut, maintenance).
  - Target daily calories (or auto-calculated from TDEE/multiplier).
  - Protein target (e.g., 2.3g/kg) and Fat target (e.g., 1.0g/kg).
  - Restrictions & texture rules.
- Saves initial `data/profile.json` and initializes default `data/pantry.json`.

### Module 2: Macro & Caloric Engine (`tools/macro_calculator.py`)
- Daily calorie & macro target computation:
  - Protein = `bodyweight_kg * protein_multiplier` (e.g., `65 * 2.3 = 149.5g` -> `150g`).
  - Fat = `bodyweight_kg * fat_multiplier` (e.g., `65 * 1.0 = 65g` -> `65-70g`).
  - Carbs = `(daily_calories - (Protein * 4) - (Fat * 9)) / 4`.
- Carbs and fats remain flat across the 7 days; protein source weights are solved to hit the target.

### Module 3: Meal Plan & Grocery Generator (`tools/meal_generator.py`, `tools/grocery_planner.py`)
- 7-Day Saturday-to-Friday schedule:
  - **Breakfast (Daily):** Soft/liquid (e.g., ON Whey + fortified soy milk + oats/avocado blend, or soft congee).
  - **Lunch (Sat & Sun):** Fresh savory solid meals (e.g., Gà xào sả ớt cooked fresh).
  - **Lunch (Mon–Wed):** Sunday evening batch-cooked reheatable Vietnamese meal (e.g., Thịt kho with pork & eggs).
  - **Lunch (Thu–Fri):** Wednesday evening batch-cooked reheatable meal (e.g., Gà xào sả ớt with jasmine rice).
  - **Dinner (Daily):** Soft/broth-based (e.g., Phở bò with thinly sliced raw beef in hot broth, rice noodles with poached shrimp).
- Zero-waste package allocation: All perishable packages (e.g. 1kg frozen shrimp, 500g chicken packs) are distributed evenly across dinner or batch lunch slots.
- Split shopping lists:
  - **Saturday Run:** Sat/Sun meals, Sun batch prep, Sat–Tue fresh meat.
  - **Wednesday Run:** Wed batch prep, Wed–Fri fresh meat.
  - **Pantry Restock:** Bulk items flagged when low.
- Outputs `data/meal_plan.csv` and `data/grocery_list.csv`.

### Module 4: Bookkeeping & Analytics (`tools/tracker.py`)
- Maintains `data/prices.csv` with unit prices (e.g., ON Whey €/kg, Colruyt chicken breast €/kg).
- Logs consumed meals in `data/meal_logs.csv`.
- Generates trend reports: weekly protein expenditure, grocery spend vs. budget, caloric adherence.

### Module 5: Dynamic Adaptation & Time Awareness (`tools/adaptation.py`)
- Uses user's configured timezone and current clock time to evaluate relative dates:
  - e.g., "Thursday night double shake instead of dinner" -> marks Thursday dinner as consumed shake, computes macro difference, rolls over unused beef/shrimp to Friday or weekend, recalculates Friday macros to balance weekly targets.
- Price/inventory adjustments: "Pork shoulder was €15/kg so bought extra chicken" -> updates price tracker and swaps lunch protein source while adjusting raw weights to maintain macro targets.

---

## 5. Builder Calls Settled
- **Planning Cycle:** Saturday-to-Friday week cleanly aligning with Saturday morning grocery run.
- **Weekend Lunches:** Saturday & Sunday lunches are scheduled as fresh solid savory meals.
- **Calorie Input:** Onboarding accepts direct target calories or computes standard default if preferred.
- **Bulk Staples:** Managed via `data/pantry.json` so bulk purchases do not distort weekly grocery spend.
- **Recipe Catalog:** Seeded with core Vietnamese dishes and staple ingredients in `meal_planner/catalog/`, dynamically extensible by the agent.
