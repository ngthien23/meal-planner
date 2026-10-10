# AI Meal & Grocery Planner Agent

An intelligent, macro-accurate, vision-enabled, and zero-waste dietary, memory, and financial planner designed for strength athletes and powerlifters. Built with **Google ADK (Agent Development Kit)** and powered by **Google Gemini** (`gemini-3.8-flash`) using your `GEMINI_API_KEY`.

---

## 🌟 Key Features

1. **Google ADK Playground & Multimodal Vision Support:**
   - Runs directly in the **Google ADK Playground** web UI (`http://127.0.0.1:8080/dev-ui/?app=meal_planner`).
   - **Grocery Bills / Receipts:** Upload photos of your store bills (Colruyt, Delhaize, etc.). The agent extracts line items and unit prices for protein sources and staples, automatically invoking price-tracking tools and logging spend.
   - **Meal Photos:** Upload photos of what you ate. The agent visually estimates calories and protein based on portion sizes, matches or adapts against your daily plan, rebalances macros, and flags unused perishable meat to roll over or freeze.

2. **Relevant Information Startup Hydration:**
   - When a conversation starts, only relevant context files are loaded:
     - **Athlete Preferences (`data/profile.json`):** Bodyweight, target calories, macro multipliers, and dietary bans.
     - **Current Week Meal Plan (`data/plans/YYMMDD_meal_plan.csv`):** The isolated active weekly plan for the current cycle.
     - **Active Weekly Memory (`data/memory/weekly.json`) & Durable Facts (`data/memory/long_term.json`)**.
   - Benchmarks disk loading with microsecond resolution (`X.X ms`) without loading unrelated pantry inventories or past weeks' logs.

3. **Two-Tier Memory System with Noise Discrimination:**
   - **Short-Term (Weekly) Memory (`data/memory/weekly.json`):** Tracks temporary physical fatigue (e.g., lower back tightness), schedule shifts, and perishable meat roll-overs for the active cycle.
   - **Long-Term (Monthly/Yearly) Memory (`data/memory/long_term.json`):** Durable athlete facts, permanent intolerances, and macro milestones that persist across conversations.
   - **Relevance Filter:** Rejects pleasantries and trivial chatter (`"ok"`, `"thanks"`, `"sounds good"`, greetings) to prevent memory pollution.

4. **Dated Weekly Plan Artifacts (`YYMMDD` Isolated Files):**
   - Saves active weekly schedules to isolated files named with the Saturday cycle start date: `data/plans/YYMMDD_meal_plan.csv` and `data/plans/YYMMDD_grocery_list.csv` (e.g., `data/plans/261010_meal_plan.csv`).
   - Keeps your weekly reading isolated and clean so you are not overwhelmed by historical weeks.
   - Automatically checks for an existing cycle file before generating a new one.

5. **Concise, Artifact-Pointing Conversational Persona:**
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
*(Or install directly: `pip install google-genai google-adk python-dotenv tzdata`)*

### 3. Configure Gemini API Key
You can set your Gemini API key in multiple ways:
- **Interactive First-Run Prompt:** Run `python main.py` directly; if no key is detected, it prompts you and can save it to `.env`.
- **Environment File:** Put `GEMINI_API_KEY=your_key_here` into `.env`.
- **Shell Variable:**
  ```powershell
  $env:GEMINI_API_KEY="your_gemini_api_key_here"
  ```

### 4. Serve the Agent in Google ADK Playground
Launch the ADK Playground web server:
```bash
python main.py
```
*(Or run `agents-cli playground`)*

On startup, you will see the benchmarked hydration log for relevant files:
```
[*] Hydrating relevant context files from blank slate...
  - [Loaded] Athlete Preferences: data\profile.json (0.24 ms)
  - [Loaded] Current Week Meal Plan: data\plans\261010_meal_plan.csv (0.35 ms)
  - [Loaded] Active Weekly Memory: data\memory\weekly.json (0.12 ms)
  - [Loaded] Durable Long-term Facts: data\memory\long_term.json (0.15 ms)
[OK] Relevant context hydrated in 0.86 ms.
[*] Active weekly meal plan artifact verified: data\plans\261010_meal_plan.csv

======================================================================
[*] Launching Google ADK Playground at: http://127.0.0.1:8080/dev-ui/?app=meal_planner
    - Chat with your Meal Planner agent in the visual playground
    - Upload photos of grocery bills/receipts to log prices or substitutions
    - Upload photos of meals to estimate calories/protein and adapt your plan
======================================================================
```

Open your browser to `http://127.0.0.1:8080/dev-ui/?app=meal_planner` to interact with the agent and upload photos!

### 5. Alternative: Terminal CLI Mode
If you prefer the terminal text interface, run:
```bash
python main.py --cli
```

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

The test suite runs with standard library `unittest`:
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
All **35 tests** pass with 100% coverage across:
- ADK playground `root_agent` instantiation and discovery
- Multimodal bill/receipt and meal photo instruction injection
- Relevant-only startup hydration benchmarking
- Macro & raw-weight solvers
- Texture & zero-waste packaging constraints
- Food safety 72h fridge meat limits & split grocery logistics
- Two-tier memory discrimination & dated `YYMMDD` weekly artifact isolation
- Dynamic deviations & price substitutions
