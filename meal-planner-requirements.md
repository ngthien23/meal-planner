# AI Meal & Grocery Planner Agent: Requirements Specification

## 1. Core Objective
To act as an intelligent, conversational dietary, logistics, and grocery planning assistant powered by Google ADK and Gemini. The LLM is the chef, nutritionist, and decision-maker. It dynamically designs weekly meal schedules, manages protein stock, and balances budgets based on the user's conversational input and preferences, using simple Markdown memories and CSV artifacts without rigid algorithmic rule engines.

---

## 2. Core Architecture: LLM as Planner & Decision-Maker
All planning, recipe design, macro balancing, price estimation, and substitution decisions are performed by LLM reasoning, not Python algorithmic heuristics or local databases:
- **No Programmatic Solvers:** No combinatorial recipe engines, hardcoded ingredient catalogs, or rigid macro constraint solvers in Python.
- **LLM Train of Thought:** When planning or adapting meals:
  1. **Consider the Budget:** Base grocery planning around the user's weekly budget for protein (e.g. €40–€50/week) stored in Long-Term Memory. Estimate ingredient costs using internal knowledge and web browsing.
  2. **Balance Needs & Preferences:** Allocate budget to core protein essentials first (chicken, eggs, meat, fish, tofu, whey powder), balanced with personal qualitative preferences stored in Long-Term Memory. Daily macros are treated as rough targets with even meat portioning prioritized over decimal precision; deficits are topped up with protein powder.
  3. **Nutrition Nuances:** Account for raw vs. cooked weight yields, bone-in/skin-on fractions, and edible portions without requiring a local nutrition facts database.
- **Stock Tracking Scope vs. Grocery List Scope:**
  - **On-Hand Stock:** Tracked in Short-Term Memory (`weekly.md`) strictly for **PROTEIN ONLY** (meats, fish, eggs, tofu, protein powder) with dates. Non-protein items (produce, carbs, oils) are ignored for fridge stock bookkeeping.
  - **Weekly Grocery List:** Must comprehensively include **ALL** food types (proteins, carbs, vegetables, fruits, pantry staples, seasonings).

---

## 3. Two-Tier Markdown Memory System
Memory is maintained entirely in human-readable Markdown files in `data/memory/`:
1. **Long-Term Memory (`data/memory/long_term.md`):**
   - Durable user facts: bodyweight, fitness goal, daily target calories, weekly protein budget, lasting dietary preferences, food intolerances, and milestones.
   - Populated during initial conversational onboarding and updated when user shares lasting habits.
2. **Short-Term Memory (`data/memory/weekly.md`):**
   - Active week context: dated on-hand protein stock (e.g. `- [YYYY-MM-DD] Stock on hand: 500g Chicken Thighs`), meal deviations (skipped meals, eating out), temporary schedule shifts, and carried calorie/protein deficits.
   - Reset or archived per weekly planning cycle.
3. **Noise Discrimination:**
   - Trivial conversational pleasantries (e.g. "ok", "thank you", "sounds good", "hello") are filtered out to prevent memory pollution.

---

## 4. Human-Readable CSV Artifacts
All operational plans are written directly to and read from CSV files in `data/plans/` (and mirrored to `data/` for active access):
1. **Weekly Meal Plan (`meal_plan.csv`):**
   - Columns: `Date, Meal, Recipe, Ingredient, P, C, F, Calories`
   - All ingredient amounts in recipes dictate raw/dry weights.
2. **Weekly Batch Cook Plan (`batch_cook.csv`):**
   - Columns: `Dish, Main_Protein, Meals`
   - Specifies only the dish name, the main protein and raw weight, and the number of meals covered.
3. **Weekly Split Grocery List (`grocery_list.csv`):**
   - Columns: `Run, Category, Item, Quantity_g, Estimated_Price_EUR`
   - Grouped into floating shopping runs (every 3–4 days to respect shelf-life limits, e.g. Saturday Run, Wednesday Run, or dated runs like `2026-10-13 Run`).
   - Automatically post-processed and sorted by `[Run, Category]` upon writing.

---

## 5. Tool Suite: Pure I/O Primitives
The agent interacts with the filesystem through exactly 7 pure I/O tools:
1. `tool_save_memory_note(note: str, tier: str)`: Saves meaningful notes to `weekly` or `long_term` memory.
2. `tool_get_meal_plan(target_date: Optional[str])`: Reads the active meal plan CSV (returns empty if file does not exist).
3. `tool_update_meal_plan(meal_entries: list[dict])`: Writes or updates rows in the active meal plan CSV.
4. `tool_get_grocery_list()`: Reads the active grocery list CSV.
5. `tool_update_grocery_list(grocery_entries: list[dict], mode: str)`: Writes or updates rows in the active grocery list CSV and sorts by `[Run, Category]`.
   - **User Confirmation Required:** The agent must always ask the user for confirmation before executing `tool_update_grocery_list`.
6. `tool_get_batch_cook()`: Reads the active batch cook CSV.
7. `tool_update_batch_cook(dishes: list[dict])`: Writes or updates rows in the active batch cook CSV.

No tools perform algorithmic calculations, combinatorial recipe solving, or programmatic decision-making.

---

## 6. Temporal Anchoring & Single Time Recording
- Time is anchored to the user's local timezone (e.g. `Europe/Brussels`).
- The current time is recorded **once** at session startup / agent initialization to prevent Google ADK from regenerating dynamic system instructions on every conversational turn.
- System instructions are passed as a static string to the ADK `Agent`.

---

## 7. Interfaces & Setup
- **Global Command (`meals`):** Launches the Google ADK Web Playground (`meals`) or terminal CLI (`meals --cli`).
- **Clean Setup (`meals --setup`):** Prompts for Gemini API key with a direct prompt (`Enter Gemini API key: `) without unsolicited suggestions or masked placeholders.