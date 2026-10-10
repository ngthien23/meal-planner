# AI Meal & Grocery Planner Agent

An intelligent, macro-accurate, and zero-waste dietary and financial planner designed for strength athletes and powerlifters. Built with **Google ADK (Agent Development Kit)** and powered by **Google Gemini** using your `GEMINI_API_KEY`.

---

## 🌟 Key Features

1. **Interactive Onboarding & Timezone Awareness (Module 1):**
   - On first launch, the agent walks you through an onboarding setup to gather your timezone (e.g. `Europe/Brussels`), current bodyweight, goal state, calorie targets, and dietary restrictions.
   - Anchors all temporal queries (`"tonight"`, `"tomorrow's lunch"`, `"Thursday night"`) to your real-time clock.
   - Strictly enforces texture and fatigue rules: **soft, liquid, or broth-based meals for breakfast and dinner** (smoothies, Phở), and **solid, batch-cooked meals for lunch** (Gà xào sả ớt, Thịt kho).
   - Enforces ingredient rules: Fortified soy milk only (no dairy), Optimum Nutrition whey only, canned tuna only.

2. **Deterministic Macro & Caloric Engine (Module 2):**
   - Calculates daily calorie, protein, fat, and carb targets dynamically.
   - Keeps carbs and fats flat across the 7-day schedule, adjusting raw protein weights (chicken breast, flank beef, pork shoulder, shrimp) to hit exact targets.

3. **Zero-Waste Plan Generation & Raw Weight Precision (Module 3):**
   - Dictates **raw and dry weights** (e.g. `110g dry pho noodles`, `200g raw lean beef`).
   - Automatically exhausts retail package sizes (e.g., exactly 1kg frozen shrimp across 4 dinners) to eliminate perishable waste.
   - Exports the full 7-day schedule to `data/meal_plan.csv`.

4. **Split Grocery Logistics & Food Safety (Module 3 & 4):**
   - Fresh meat is never stored in the fridge longer than 48–72 hours.
   - Automatically divides shopping runs into:
     - **Saturday Run:** Sat/Sun meals, Sunday batch prep (Mon–Wed lunches), and Sat–Tue fresh meats.
     - **Wednesday Run:** Wed batch prep (Thu–Fri lunches) and Wed–Fri fresh meats.
     - **Pantry Restock:** Bulk staples (2.27kg ON Whey tub, 5kg rice bags, cooking oil) tracked via `data/pantry.json` and restocked only when running low.
   - Exports itemized shopping list to `data/grocery_list.csv`.

5. **Bookkeeping, Price Tracking & Analytics (Module 4):**
   - Logs unit prices to `data/prices.csv`.
   - Records consumed meals and deviations in `data/meal_logs.csv`.
   - Generates analytics on weekly protein spending and caloric adherence.

6. **Real-Time Dynamic Adaptation (Module 5):**
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
Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
Or set the environment variable in PowerShell:
```powershell
$env:GEMINI_API_KEY="your_gemini_api_key_here"
```

### 4. Run the Agent
Start the interactive terminal CLI:
```bash
python main.py
```

On first run, the agent will guide you through onboarding and immediately generate your local CSV artifacts in the `data/` directory.

---

## 📁 Artifacts & Data Directory

All persistent state is stored in clean, human-readable CSV and JSON files in the `data/` folder:

| File | Description |
|------|-------------|
| `data/profile.json` | User profile, timezone, bodyweight, macro multipliers, and dietary rules |
| `data/meal_plan.csv` | 7-day meal plan with raw/dry ingredient weights and macros |
| `data/grocery_list.csv` | Split shopping lists (Saturday Run, Wednesday Run, Pantry Restock) |
| `data/prices.csv` | Unit price tracker for staple ingredients |
| `data/meal_logs.csv` | Historical log of meals, deviations, and adherence |
| `data/pantry.json` | Stock levels and reorder thresholds for bulk pantry items |

---

## 🧪 Running Tests

The test suite runs with standard library `unittest` and requires no extra test runner:
```bash
python -m unittest discover -s tests -p "test_*.py" -v
```
All 15 tests cover macro calculations, texture constraints, food safety limits, pantry reordering, and dynamic schedule adaptation.
