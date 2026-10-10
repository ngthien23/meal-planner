# AI Meal & Grocery Planner Agent

An intelligent, macro-accurate, vision-enabled, and zero-waste dietary, memory, and financial planner designed for strength athletes and powerlifters. Built with **Google ADK (Agent Development Kit)** and powered by **Google Gemini** (`gemini-3.8-flash`) using your `GEMINI_API_KEY`.

---

## ⚡ Instant Shortcut: `meals`

Launch the app with a single word. Running `meals` automatically starts the Google ADK server and **immediately opens the visual playground in your default browser**:

```bash
meals
```

Cross-platform convenience options:
- **Windows Command Prompt:** `meals` (executes `meals.bat`)
- **Windows PowerShell:** `.\meals` or `meals` (executes `meals.ps1`)
- **macOS / Linux:** `./meals` (executes `meals` bash script)
- **Direct Python:** `python main.py`

### Useful Flags
- `meals` : Launch Google ADK Playground and open in default browser.
- `meals --setup` : Re-run the interactive Quick Setup wizard to adjust goals, timezone, currency, or API keys.
- `meals --cli` : Launch the interactive terminal text interface instead of the web playground.
- `meals --no-browser` : Start the web server without automatically popping up the browser.
- `meals --port=8080` : Run on a custom port.

---

## 🌟 Quick Setup for New Users (GitHub Clones)

When cloning fresh from GitHub, the repository comes with zero pre-existing user data (`.gitignore` protects your `.env` and `data/` directories).

On first run (or via `meals --setup`), an interactive **Quick Setup Wizard** walks you through:

1. **Gemini API Key:** Prompts for your API key (get a free key at [Google AI Studio](https://aistudio.google.com/app/apikey)) and automatically saves it to `.env`.
2. **Timezone:** Auto-detects your system timezone with clean fallback (`Europe/Brussels`, `UTC`, `America/New_York`, `Asia/Ho_Chi_Minh`, etc.).
3. **Currency:** Select your preferred currency (`EUR €`, `USD $`, `GBP £`, `VND ₫`, `CAD CA$`, `AUD A$`, `JPY ¥`, `CHF`).
4. **Cycle Start Day & Retention Window:** Pick which day starts your week (`Monday`, `Saturday`, `Sunday`) and how many weeks ahead to plan.
5. **Physical Profile & Goals:** Set your bodyweight and target (`maintenance`, `lean_bulk`, `cut`). Daily calories can be auto-estimated or explicitly entered.
6. **Dietary Restrictions:** **Clean empty default** (`[]`). No unsolicited bans are imposed; easily specify your own comma-separated allergies or restrictions if desired.

---

## 🌟 Key Features

1. **Google ADK Playground & Multimodal Vision Support:**
   - Runs in the **Google ADK Playground** web UI (`http://127.0.0.1:8080/dev-ui/?app=meal_planner`).
   - **Grocery Bills / Receipts:** Upload photos of your receipts. The agent extracts line items and unit prices, invoking price-tracking tools and logging spend.
   - **Meal Photos:** Upload photos of what you ate. The agent visually estimates calories and protein, rebalances macros, and flags unused perishable meat to roll over or freeze.

2. **Relevant Information Startup Hydration:**
   - When a conversation starts, only relevant context files are loaded:
     - **Athlete Preferences (`data/profile.json`):** Bodyweight, target calories, macro multipliers, and dietary rules.
     - **Current Week Meal Plan (`data/plans/YYMMDD_meal_plan.csv`):** The isolated active weekly plan for the current cycle.
     - **Active Weekly Memory (`data/memory/weekly.json`) & Durable Facts (`data/memory/long_term.json`)**.
   - Benchmarks disk loading with microsecond resolution (`X.X ms`) without loading unrelated pantry inventories or past weeks' logs.

3. **Strict Formatted Weekly Artifacts (`YYMMDD` Isolated Files):**
   - **Weekly Meal Plan:** Strict 8 columns: `[Date, Meal, Recipe, Ingredient, P, C, F, Calories]` with clean integer rounded grams.
   - **Weekly Batch Cook File:** Strict 5 columns: `[Dish, Ingredient, Grocery_Run, Prep_Day, Days_Served]`.
   - **Weekly Split Grocery List:** Grouped strictly by `[Run, Category]` with date-only runs (`Saturday`, `Wednesday`, `Pantry`) and currency symbol formatting.
   - Files only exist for current and next week (`weeks_ahead = 1` default) to prevent historical clutter.

4. **Two-Tier Memory System with Noise Discrimination:**
   - **Short-Term (Weekly) Memory (`data/memory/weekly.json`):** Tracks temporary fatigue, schedule shifts, and perishable roll-overs.
   - **Long-Term Memory (`data/memory/long_term.json`):** Durable athlete facts, permanent intolerances, and macro milestones.
   - **Relevance Filter:** Rejects pleasantries and trivial chatter (`"ok"`, `"thanks"`, `"sounds good"`, greetings) to prevent memory pollution.

5. **Food Discovery & Real-Time Addition:**
   - Agent dynamically discovers foods from real updates and bills, asks for your confirmation, and adds them to the ingredient catalog with macros and package sizes.

6. **Vegetable & Fruit Macro Tracking:**
   - Tracks total vegetable and fruit intake in daily plans, consumption logs, and analytics summaries.

---

## 🚀 Installation & First Run

### 1. Requirements
- Python 3.10+ (tested on Python 3.13)
- Gemini API key (`GEMINI_API_KEY`)

### 2. Quick One-Command Setup
Clone the repository and run the setup script:

```bash
git clone https://github.com/your-username/meal-planner.git
cd meal-planner
```

**PowerShell:**
```powershell
.\setup.ps1
```

**Windows Command Prompt:**
```bat
setup.bat
```

**Or using uv / pip:**
```bash
uv pip install -e .
# or
pip install -e .
```

### 3. Launch
Once set up, run:
```bash
meals
```
*(In PowerShell without running setup first, run `.\meals` or `python main.py`)*

On first launch, the wizard configures your preferences and generates your initial weekly plan artifacts.

---

## 📁 Artifacts & Data Directory

All persistent state is stored in clean, human-readable CSV and JSON files in the `data/` folder:

| File | Description |
|------|-------------|
| `data/profile.json` | User profile, timezone, currency, bodyweight, macro multipliers, and dietary rules |
| `data/plans/YYMMDD_meal_plan.csv` | Active isolated weekly meal plan (`[Date, Meal, Recipe, Ingredient, P, C, F, Calories]`) |
| `data/plans/YYMMDD_batch_cook.csv` | Active batch-cook preparation plan (`[Dish, Ingredient, Grocery_Run, Prep_Day, Days_Served]`) |
| `data/plans/YYMMDD_grocery_list.csv` | Active isolated weekly split grocery list grouped by `[Run, Category]` |
| `data/memory/weekly.json` | Short-term weekly memory notes and deviations |
| `data/memory/long_term.json` | Long-term athlete preferences, food intolerances, and milestones |
| `data/prices.csv` | Unit price tracker for staple ingredients |
| `data/meal_logs.csv` | Historical log of meals, deviations, vegetable/fruit grams, and adherence |
| `data/pantry.json` | Stock levels and reorder thresholds for bulk pantry items |

---

## 🧪 Running Tests

The test suite runs with standard library `unittest`:
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
All **51 unit tests** pass with 100% coverage across:
- Quick setup wizard & default empty preferences
- Currency formatting & timezone normalization
- `meals` CLI shortcut & automatic browser launch
- ADK playground `root_agent` instantiation and discovery
- Multimodal receipt and meal photo instruction injection
- Relevant-only startup hydration benchmarking
- Strict 8-column weekly meal plan and 5-column batch cook CSV formats
- Grouped split grocery runs (`[Run, Category]`)
- Vegetable & fruit macro tracking
- Food item discovery and confirmation
- Food safety 72h fridge meat limits & dynamic deviations
