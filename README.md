# AI Meal & Grocery Planner Agent

An intelligent, macro-accurate, and zero-waste dietary, memory, and financial planner designed for strength athletes and powerlifters. Built with **Google ADK (Agent Development Kit)** and powered by **Google Gemini** (`gemini-3.8-flash`) using your `GEMINI_API_KEY`.

---

## 🌟 Key Features

1. **Interactive Onboarding & Timezone Awareness (Module 1):**
   - On first launch, the agent walks you through an onboarding setup to gather your timezone (e.g. `Europe/Brussels`), current bodyweight, goal state, calorie targets, and dietary restrictions.
   - Anchors all temporal queries (`"today"`, `"tonight"`, `"tomorrow's lunch"`, `"Thursday night"`) to your real-time clock.
   - Strictly enforces texture and fatigue rules: **soft, liquid, or broth-based meals for breakfast and dinner** (smoothies, Phở), and **solid, batch-cooked meals for lunch** (Gà xào sả ớt, Thịt kho).
   - Enforces ingredient rules: Fortified soy milk only (no dairy), Optimum Nutrition whey only, canned tuna only.

2. **Two-Tier Memory System with Noise Discrimination:**
   - **Short-Term (Weekly) Memory (`data/memory/weekly.json`):** Tracks temporary physical fatigue (e.g., lower back tightness), schedule shifts, and perishable meat roll-overs for the active cycle.
   - **Long-Term (Monthly/Yearly) Memory (`data/memory/long_term.json`):** Durable athlete facts, permanent intolerances, and macro milestones that persist across conversations.
   - **Relevance Filter:** Rejects pleasantries and trivial chatter (`"ok"`, `"thanks"`, `"sounds good"`, greetings) to prevent memory pollution.

3. **Dated Weekly Plan Artifacts (`YYMMDD` Isolated Files):**
   - Saves active weekly schedules to isolated files named with the Saturday cycle start date: `data/plans/YYMMDD_meal_plan.csv` and `data/plans/YYMMDD_grocery_list.csv` (e.g., `data/plans/261010_meal_plan.csv`).
   - Keeps your weekly reading isolated and clean so you are not overwhelmed by historical weeks.
   - Automatically checks for an existing cycle file before generating a new one.

4. **Transparent Blank-Slate Startup Hydration:**
   - Each session starts from a clean slate and benchmarks loading every state file from disk.
   - Prints benchmarked hydration latency with millisecond precision (`X.X ms`) before the prompt opens.

5. **Concise, Artifact-Pointing Conversational Style:**
   - When asked about your schedule or grocery list (e.g., *"what is my schedule for this week?"*), the agent points directly to the active artifact path.
   - Tabular meal rows and full CSV contents are only printed in chat upon explicit request (e.g. *"print the plan in chat"*).

6. **Deterministic Macro & Caloric Engine (Module 2):**
   - Calculates daily calorie, protein, fat, and carb targets dynamically.
   - Keeps carbs and fats flat across the 7-day schedule, adjusting raw protein weights (chicken breast, flank beef, pork shoulder, shrimp) to hit exact targets.

7. **Zero-Waste Plan Generation & Raw Weight Precision (Module 3):**
   - Dictates **raw and dry weights** (e.g. `110g dry pho noodles`, `200g raw lean beef`).
   - Automatically exhausts retail package sizes (e.g., exactly 1kg frozen shrimp across 4 dinners) to eliminate perishable waste.

8. **Split Grocery Logistics & Food Safety (Module 3 & 4):**
   - Fresh meat is never stored in the fridge longer than 48–72 hours.
   - Automatically divides shopping runs into:
     - **Saturday Run:** Sat/Sun meals, Sunday batch prep (Mon–Wed lunches), and Sat–Tue fresh meats.
     - **Wednesday Run:** Wed batch prep (Thu–Fri lunches) and Wed–Fri fresh meats.
     - **Pantry Restock:** Bulk staples (2.27kg ON Whey tub, 5kg rice bags, cooking oil) tracked via `data/pantry.json` and restocked only when running low.

9. **Bookkeeping, Price Tracking & Analytics (Module 4):**
   - Logs unit prices to `data/prices.csv`.
   - Records consumed meals and deviations in `data/meal_logs.csv`.
   - Generates analytics on weekly protein spending and caloric adherence.

10. **Real-Time Dynamic Adaptation (Module 5):**
    - Seamlessly handles deviations: e.g., *"I was too tired Thursday night and drank a double shake instead"* -> recalculates Friday macros, checks shelf-life of unused fresh meat, and flags it to roll over or freeze.
    - Handles grocery substitutions: e.g., *"Pork shoulder was €15/kg today so I bought extra chicken"* -> recalculates lunches and raw protein weights.

---

## 🚀 Quick Start

### 1. Requirements
- Python 3.10+ (tested on Python 3.13)
- Gemini API key (`GEMINI_API_KEY`)

### 2. Installation
Install project dependencies:
```bash
pip install -e .
```
*(Or install directly: `pip install google-genai python-dotenv tzdata`)*

### 3. Configure Gemini API Key
You can set your Gemini API key in multiple ways:
- **Interactive First-Run Prompt:** Run `python main.py` directly; if no key is detected, it prompts you and can save it to `.env`.
- **Environment File:** Put `GEMINI_API_KEY=your_key_here` into `.env`.
- **Shell Variable:**
  ```powershell
  $env:GEMINI_API_KEY="your_gemini_api_key_here"
  ```

### 4. Run the Agent
Start the interactive terminal CLI:
```bash
python main.py
```

On startup, you will see the benchmarked blank-slate hydration log:
```
[*] Hydrating memory & bookkeeping files from blank slate...
  - [Loaded] Profile: data\profile.json (0.24 ms)
  - [Loaded] Weekly Memory: data\memory\weekly.json (0.12 ms)
  - [Loaded] Long-term Memory: data\memory\long_term.json (0.15 ms)
  - [Loaded] Pantry Inventory: data\pantry.json (0.18 ms)
  - [Loaded] Active Weekly Plan: data\plans\261010_meal_plan.csv (0.42 ms)
[OK] Memory & artifacts hydrated in 1.11 ms.
[*] Active weekly meal plan artifact verified: data\plans\261010_meal_plan.csv
[AI] Gemini Agent (gemini-3.8-flash) is active and ready!
```

---

## 💬 Interactive CLI Commands

In addition to open natural language conversation, the CLI supports fast shortcut commands:
- `/plan`: Re-generate or view active weekly plan files
- `/groceries`: View current split grocery list (Saturday / Wednesday / Pantry)
- `/analytics`: View protein spend and adherence summary
- `/memory`: Inspect active short-term (weekly) and long-term memory notes
- `/exit`: Exit the session

---

## 📁 Artifacts & Data Directory

All persistent state is stored in clean, human-readable CSV and JSON files in the `data/` folder:

| File | Description |
|------|-------------|
| `data/profile.json` | User profile, timezone, bodyweight, macro multipliers, and dietary rules |
| `data/plans/YYMMDD_meal_plan.csv` | Active isolated weekly meal plan (e.g. `261010_meal_plan.csv`) |
| `data/plans/YYMMDD_grocery_list.csv` | Active isolated weekly split grocery list |
| `data/memory/weekly.json` | Short-term weekly memory notes and deviations |
| `data/memory/long_term.json` | Long-term athlete preferences, food intolerances, and milestones |
| `data/prices.csv` | Unit price tracker for staple ingredients |
| `data/meal_logs.csv` | Historical log of meals, deviations, and adherence |
| `data/pantry.json` | Stock levels and reorder thresholds for bulk pantry items |

---

## 🧪 Running Tests

The test suite runs with standard library `unittest` and requires no extra test runner:
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
All **31 tests** pass with 100% coverage across:
- Macro & raw-weight solvers
- Texture & zero-waste packaging constraints
- Food safety 72h fridge meat limits & split grocery logistics
- Two-tier memory discrimination & hydration benchmarks
- Dated `YYMMDD` weekly artifact isolation
- Dynamic deviations & price substitutions
