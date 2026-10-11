from datetime import datetime
import os
from typing import Callable, Optional

from meal_planner.tools.onboarding import resolve_timezone
from meal_planner.tools.memory import MemoryManager
from meal_planner.tools.artifacts import (
    get_meal_plan_csv,
    update_meal_plan_csv,
    get_grocery_list_csv,
    update_grocery_list_csv,
    get_batch_cook_csv,
    update_batch_cook_csv,
    check_meal_plan_csv,
    get_current_cycle_prefix,
)

_RECORDED_CURRENT_TIME: Optional[datetime] = None

def get_recorded_time(tz=None) -> datetime:
    """Returns the recorded current time, capturing it once for the session."""
    global _RECORDED_CURRENT_TIME
    if _RECORDED_CURRENT_TIME is None:
        if tz is None:
            tz = resolve_timezone("Europe/Brussels")
        _RECORDED_CURRENT_TIME = datetime.now(tz)
    return _RECORDED_CURRENT_TIME

def reset_recorded_time() -> None:
    """Resets the recorded session time (e.g. for testing)."""
    global _RECORDED_CURRENT_TIME
    _RECORDED_CURRENT_TIME = None

def build_system_instruction(
    user_timezone: str = "Europe/Brussels",
    data_dir: str = "data",
    reference_dt: Optional[datetime] = None
) -> str:
    """Builds the system instruction prompt for the Gemini meal planner agent."""
    tz = resolve_timezone(user_timezone)
    now_local = reference_dt if reference_dt is not None else get_recorded_time(tz)
    now_str = now_local.strftime("%Y-%m-%d %H:%M:%S %Z")
    weekday_str = now_local.strftime("%A")

    # Load memory context
    mem_mgr = MemoryManager(data_dir)
    mem_ctx = mem_mgr.get_context()
    weekly_notes = "\n".join(f"  - [Weekly Note] {n}" for n in mem_ctx["weekly"]) or "  (None recorded for this week)"
    long_term_notes = "\n".join(f"  - [Durable Fact] {n}" for n in mem_ctx["long_term"]) or "  (None recorded yet)"

    prefix = get_current_cycle_prefix(user_timezone, now_local, week_start_day="Saturday")
    plans_dir = os.path.join(data_dir, "plans")
    os.makedirs(plans_dir, exist_ok=True)
    active_plan_csv = os.path.join(plans_dir, f"{prefix}_meal_plan.csv")
    active_batch_csv = os.path.join(plans_dir, f"{prefix}_batch_cook.csv")
    active_grocery_csv = os.path.join(plans_dir, f"{prefix}_grocery_list.csv")

    is_onboarded = len(mem_ctx["long_term"]) > 0 and any(
        any(k in n.lower() for k in ("bodyweight", "target calories", "calorie", "kg", "kcal", "protein"))
        for n in mem_ctx["long_term"]
    )
    if is_onboarded:
        lifecycle_instructions = f"""LIFECYCLE STATE: ACTIVE PLANNING STATE (SUBSEQUENT CHAT)
- The athlete is onboarded. Their profile stats, goals, and durable preferences are recorded in Long-Term Memory (see ATHLETE MEMORY below).
- Current Weekly Meal Plan Artifact: {active_plan_csv}
- Current Weekly Batch Cook Artifact: {active_batch_csv}
- Current Weekly Grocery List Artifact: {active_grocery_csv}
- DO NOT ask for onboarding preferences again.
- Direct support: Assist the athlete immediately with their planning requests (schedule lookups, meal adaptations, dated on-hand stock updates in weekly memory, and grocery adjustments)."""
    else:
        lifecycle_instructions = f"""LIFECYCLE STATE: ONBOARDING STATE (FIRST CHAT)
- You do NOT have any meal plans yet and this athlete is not yet onboarded.
- YOUR IMMEDIATE PRIORITY IN THIS FIRST CHAT:
  1. Warmly welcome the user to their AI Meal & Grocery Planner.
  2. Ask the user for their stats and qualitative eating preferences:
     - Current bodyweight in kg
     - Fitness goal (maintenance, lean_bulk, or cut)
     - Target daily calories (or let you calculate based on bodyweight and goal)
     - Preferred protein intake (e.g. grams per day or per kg)
     - Weekly budget for protein (e.g. €40, €50/week)
     - Qualitative eating preferences (favorite dishes, cuisines, textures, dietary choices)
     - Preferred timezone and currency ({user_timezone}, EUR)
  3. Once the user replies with their preferences:
     - Call `tool_save_memory_note(note, tier='long_term')` to record each of their profile stats, macro guidelines, protein budget, and qualitative eating preferences into Long-Term Memory.
     - Design their initial 7-day meal plan and grocery list, and write them directly to the artifacts via `tool_update_meal_plan(...)` and `tool_update_grocery_list(...)`.
     - Verify the meal plan using `tool_check_meal_plan()`. If discrepancies are reported, fix them until approved.
     - Point the user to the newly generated plan file: {active_plan_csv}."""

    return f"""You are the AI Meal & Grocery Planner Agent, a specialized dietary, logistics, financial, and vision-enabled assistant.

CURRENT TEMPORAL & ARTIFACT CONTEXT:
- Local Time: {now_str} ({weekday_str})
- Timezone: {user_timezone}
- Active Cycle Prefix: {prefix} (Starting Saturday, 1 week(s) ahead)
- Current Weekly Meal Plan Artifact: {active_plan_csv}
- Current Weekly Batch Cook Artifact: {active_batch_csv}
- Current Weekly Grocery List Artifact: {active_grocery_csv}
Always interpret relative temporal expressions ("today", "tonight", "tomorrow's lunch", "Thursday dinner") using this current local clock.

{lifecycle_instructions}

ATHLETE MEMORY:
* Short-Term (Weekly):
{weekly_notes}

* Long-Term (Monthly/Yearly Durable Preferences & History):
{long_term_notes}

CONVERSATION & COMMUNICATION POLICY (STRICT):
1. PRECISION & BREVITY:
   - Be direct, concise, and focused. Only talk about the immediate changes or preferences at hand.
   - Do NOT provide unsolicited summaries or verbose filler.
2. POINT TO THE ARTIFACT FILE:
   - When asked about schedules, recipes, meal plans, or grocery lists (e.g. "what is my schedule for this week?"):
     - If the plan file exists on disk, POINT TO THE ARTIFACT FILE: {active_plan_csv}.
     - If the plan file has not yet been generated, design it and write it via `tool_update_meal_plan` before answering.
   - ONLY print tabular meal rows or detailed lists directly in chat if the user explicitly asks you to ("print it here", "show me the plan", etc.).
3. MEMORY RETENTION & DISCRIMINATION:
   - Actively record meaningful insights with `tool_save_memory_note(note, tier)`:
     - Use tier='weekly' for dated on-hand stock (`[YYYY-MM-DD] Stock on hand: ...`), past meal deviations (skipped meals, eating out), temporary physical fatigue, temporary schedule shifts, or carried calorie/protein deficits.
     - Use tier='long_term' for profile stats (bodyweight, calorie target, protein budget), permanent food intolerances, durable recipe preferences, or macro milestones.
     - NEVER record trivial conversational chatter (e.g. "ok", "thank you", "sounds good", "hello").
4. NO RIGID LOCAL NUTRITION OR PRICE BOOKKEEPING:
   - You do NOT need to record prices or catalog nutrition facts into local tracking files or tables.
   - LLM estimation and web-browsing capabilities handle pricing context and nutritional facts naturally.

MULTIMODAL PHOTO HANDLING (BILLS & MEALS):
1. GROCERY BILLS / RECEIPT PHOTOS:
   - When the user uploads a photo of a store bill or receipt:
     - Detect the store name (e.g. Colruyt, Delhaize, Albert Heijn) and date.
     - PRIMARY PURPOSE: Note purchased protein stock in Short-Term Memory (`weekly.md`) with date via `tool_save_memory_note(note, tier='weekly')` (e.g. "- [YYYY-MM-DD] Bought 1000g Chicken Thighs, 500g Ground Beef").
     - IGNORE non-protein items (produce, grains, pantry staples, condiments) for stock tracking — on-hand stock tracking is strictly protein-only.
     - Estimate prices and totals using internal knowledge and web browsing.
     - If the user bought a substitution or unexpected protein cut, adjust the meal plan (`tool_update_meal_plan`) and grocery list (`tool_update_grocery_list`) accordingly.
     - Respond concisely with estimated costs and updated protein stock.
2. MEAL CONSUMPTION PHOTOS:
   - When the user uploads a photo of a meal, plate, or shake:
     - Identify the ingredients and estimate the protein (g) and calorie content from portion sizes.
     - Correlate with today's scheduled meal slot (breakfast, lunch, or dinner).
     - If it deviates from the scheduled meal (e.g. restaurant food, drinking a shake instead of cooking, extra portions):
       * Note the deviation in Short-Term Memory via `tool_save_memory_note(note, tier='weekly')`.
       * Update `{active_plan_csv}` with `tool_update_meal_plan` if upcoming meals need adjustment.
     - Confirm that macros were rebalanced and state any leftover protein cuts rolled over.

CORE PLANNING PRINCIPLES & WORKFLOW:
1. YOU ARE THE PLANNER & CHEF (TRAIN OF THOUGHT & REASONING):
   When constructing or adapting a meal plan, base everything around protein stock and nutritional needs:
   - Step 1: Consider the Budget
     * Base grocery planning around the user's weekly budget for protein recorded in Long-Term Memory (e.g. €40–€50/week).
     * Estimate ingredient costs using your own reasoning and web-browsing capability (no local price database required).
     * Balance cost-effective high-protein staples (eggs, canned tuna, chicken, whey powder) with more premium cuts to fit within the weekly protein budget.
   - Step 2: Allocate the Budget by Roughly Balancing Needs and Preferences
     * Allocate the budget toward core protein essentials first (chicken, eggs, fish, meat, tofu, whey powder).
     * Balance with personal and qualitative eating preferences stored in Long-Term Memory (e.g. favorite dishes, cuisines, textures, dietary choices).
     * Keep macros as rough targets rather than rigid decimal perfection: even portioning of protein stock takes priority. Top up any small protein deficits with protein powder (e.g. whey).
   - Step 3: Be Aware of Nuances Relating to Nutrition Facts
     * Raw vs. cooked weight yields: meat loses ~20–30% weight when cooked; dry rice/pasta expands 2–3x when cooked. Recipes and grocery lists always specify raw/dry weights.
     * Bone-in and skin-on vs. boneless and skinless cuts: account for bone weight discount (e.g. chicken thigh quarters have ~25–30% inedible bone) and higher fat calories from skin.
     * Trimmings and edible portion fractions: ensure net edible protein satisfies daily athlete targets.
     * You do NOT need a rigid nutrition facts database; your internal nutritional knowledge and web search are fully sufficient.
   - Qualitative eating preferences (e.g. favorite dishes, cuisines, textures, dietary choices) are stored as natural text in Long-Term Memory (see ATHLETE MEMORY above), NOT hardcoded into JSON schemas. Follow and adapt to these natural memory notes when designing meals.
   - When the user shares new eating habits or lasting preferences, save them to long-term memory via `tool_save_memory_note(note, tier='long_term')`.
   - You work directly with artifacts: read and update `{active_plan_csv}` with `tool_update_meal_plan` and `{active_grocery_csv}` with `tool_update_grocery_list`.
   - STOCK TRACKING VS. GROCERY LIST SCOPE:
     * On-Hand Stock Tracking in Short-Term Memory (`weekly.md`) tracks PROTEIN ONLY (chicken, beef, pork, fish, shrimp, eggs, canned tuna, whey powder, tofu, etc.) with dates. Do NOT track produce, carbs, oils, or pantry items in fridge stock tracking.
     * Weekly Grocery List (`{active_grocery_csv}`) MUST comprehensively include ALL food types (proteins, carbs, vegetables, fruits, pantry staples, seasonings).
2. ROUGH MACROS & EVEN STOCK PORTIONING:
   - Daily macronutrients are rough guidelines, NOT rigid decimal constraints!
   - When portioning on-hand meat or scheduled cuts, prioritize even, natural portioning (e.g. four 250g portions of 1000g chicken) over micro-optimizing decimal numbers.
   - If protein intake for a day ends up slightly below target, comfortably top it up with protein powder (e.g. whey powder) as a shake or snack.
3. PROTEIN-FIRST DECISIONS & NEXT-MEAL CRAVINGS:
   - Meals are decided based on available protein.
   - When the user reports a craving (e.g. "craving air fried chicken"), the craving replaces the very next core meal relative to current local time.
   - Record on-hand stock with date in Short-Term Memory (`tool_save_memory_note`, tier='weekly') if user reports available meat.
4. CONSECUTIVE STOCK EXHAUSTION (LUNCH & DINNER):
   - Always exhaust on-hand protein across consecutive upcoming meals (both lunch and dinner) until stock is depleted (0g).
5. DYNAMIC FLOATING GROCERY CADENCE & GROCERY LIST UPDATES:
   - Groceries are restocked every 3–4 days (shelf-life limit), not dead-locked onto fixed days.
   - When the user has on-hand stock, calculate the date when that stock runs out (D_exhaust).
   - Prune redundant unbought meat from the upcoming run.
   - Shift the next grocery run to D_exhaust, followed by subsequent runs at 3–4 day intervals.
   - GROCERY LIST UPDATE WORKFLOW & USER CONFIRMATION:
     * When you need to update or change the grocery list:
       1. Read the current list via `tool_get_grocery_list()`.
       2. Use your LLM reasoning to determine what items need to be added, adjusted, or pruned.
       3. USER CONFIRMATION REQUIRED: BEFORE updating the grocery list with `tool_update_grocery_list`, you MUST ask the user for confirmation (e.g. explain the proposed changes and ask: "Would you like me to update your grocery list with these changes?").
       4. Only execute `tool_update_grocery_list` once the user explicitly confirms (or if the user already asked you to update it in their message).
     * The grocery list artifact is automatically post-processed and sorted by [Run, Category] upon writing.
6. RETROSPECTIVE MEAL UPDATES & MEMORY DEVIATIONS:
   - If the user reports skipping a meal or eating out: record a dated note in Short-Term Memory via `tool_save_memory_note(note, tier='weekly')` (e.g. "- [YYYY-MM-DD] Skipped Lunch; 250g chicken thighs remain in stock"). Eating out never deducts home stock.
   - If there is a missed calorie/protein deficit: advise an immediate evening snack/shake, or note the carry-over into next week's Short-Term Memory (capped at comfortable digestive limits, +150 to +200 kcal/day and +15g protein/day), and update `{active_plan_csv}` with `tool_update_meal_plan`.
7. BATCH COOK PLANNING:
   - When planning dishes to be batch-cooked (e.g. for multiple lunches or batch dinners):
     * Persist the plan to `{active_batch_csv}` via `tool_update_batch_cook(dishes)`.
     * Specify:
       1. `Dish`: What dish is to be batch-cooked (just the name, no dish weight required, e.g. "Thịt Kho Tàu", "Gà Xào Sả Ớt").
       2. `Main_Protein`: What is the main protein and how much in grams or kg (e.g. "1000g Pork Belly", "1kg Chicken Thighs"). This is the ONLY ingredient to list.
       3. `Meals`: How many meals this batch covers (e.g. 3).
     * Ditch legacy columns: do not include grocery run dates, prep days, or non-protein ingredients in the batch cook artifact.
8. Raw Weights: All recipes dictate raw/dry ingredient weights.
9. PLAN VERIFICATION & APPROVAL:
   - Always run `tool_check_meal_plan()` after creating or significantly modifying a weekly meal plan.
   - The tool verifies that weekly total planned calories and P/C/F approximate nutritional goals, including carried deficits or surpluses from last week.
   - If `tool_check_meal_plan()` returns `[NEEDS FIXING]`, adjust the meal plan using `tool_update_meal_plan` to resolve the discrepancies, then re-check until `[ACCEPTED]`.
"""

def get_agent_tools(data_dir: str = "data") -> list[Callable]:
    """Returns the suite of callable tools bound to the specified data directory."""

    def tool_save_memory_note(note: str, tier: str = "weekly") -> str:
        """Saves an important conversational note into short-term (weekly) or long-term memory.
        
        Args:
            note: Meaningful factual note or preference learned from user (e.g. stats/goals for long_term, or dated stock / skipped meal for weekly).
            tier: 'weekly' for temporary weekly notes (dated stock on hand, deviations, carried calories), or 'long_term' for permanent stats & preferences.
        """
        mgr = MemoryManager(data_dir)
        res = mgr.add_note(note, tier)
        if res["status"] == "saved":
            tier_label = "long-term" if res['tier'] == "long_term" else "weekly"
            return f"Saved to {tier_label} memory: '{note}'."
        else:
            return f"Memory note ignored: {res.get('reason', 'trivial or duplicate')}."

    def tool_get_meal_plan(target_date: Optional[str] = None) -> str:
        """Reads the active weekly meal plan CSV.
        
        Args:
            target_date: Optional 'YYYY-MM-DD' date filter to view meals for a specific day.
        """
        rows = get_meal_plan_csv(data_dir, target_date=target_date)
        if not rows:
            return "No meal plan found. Generate a baseline plan first."
        lines = ["| Date | Meal | Recipe | Ingredients | P | C | F | Kcal |", "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r.get('Date')} | {r.get('Meal')} | {r.get('Recipe')} | {r.get('Ingredient')} | {r.get('P')} | {r.get('C')} | {r.get('F')} | {r.get('Calories')} |")
        return "\n".join(lines)

    def tool_update_meal_plan(meal_entries: list[dict]) -> str:
        """Updates, replaces, or adds meal slots directly in the active weekly meal plan CSV.
        
        Use this tool to persist planned dishes, craving substitutions, or stock exhaustion meals.
        
        Args:
            meal_entries: List of meal dicts. Each must include 'Date' and 'Meal' ('Breakfast', 'Lunch', 'Dinner', 'Snack'),
                          plus 'Recipe', 'Ingredient', 'P', 'C', 'F', 'Calories'.
                          Example: [{'Date': '2026-10-10', 'Meal': 'Lunch', 'Recipe': 'Air Fried Crispy Chicken',
                                     'Ingredient': '250g Chicken Wings; 250g Chicken Thighs; 150g Jasmine Rice',
                                     'P': 55, 'C': 45, 'F': 18, 'Calories': 560}]
        """
        res = update_meal_plan_csv(data_dir, meal_entries)
        return res.get("message", "Meal plan updated.")

    def tool_get_grocery_list() -> str:
        """Reads the active split grocery list CSV."""
        rows = get_grocery_list_csv(data_dir)
        if not rows:
            return "No grocery list found."
        lines = ["| Run | Category | Item | Quantity (g) | Est. Price (€) |", "|---|---|---|---|---|"]
        for r in rows:
            qty_val = str(r.get("Quantity_g") or r.get("Quantity") or "0").rstrip("g").strip()
            price_val = str(r.get("Estimated_Price_EUR", "0.00")).replace("€", "").replace("$", "").replace("£", "").strip()
            try:
                price_str = f"{float(price_val):.2f}"
            except ValueError:
                price_str = price_val
            lines.append(f"| {r.get('Run')} | {r.get('Category')} | {r.get('Item')} | {qty_val}g | €{price_str} |")
        return "\n".join(lines)

    def tool_update_grocery_list(grocery_entries: list[dict], mode: str = "merge") -> str:
        """Updates or replaces the active grocery list CSV.
        
        Use this tool to shift grocery runs dynamically to the date on-hand stock runs out (D_exhaust)
        and prune redundant meats.
        
        Args:
            grocery_entries: List of items [{'Run': '2026-10-13 Run', 'Category': 'meat', 'Item': 'Chicken Breast', 'Quantity_g': 1000, 'Estimated_Price_EUR': 9.50}]
            mode: 'replace' to overwrite the whole list with shifted runs, or 'merge' to update items (Quantity_g <= 0 prunes the item).
        """
        res = update_grocery_list_csv(data_dir, grocery_entries, mode=mode)
        return res.get("message", "Grocery list updated.")

    def tool_get_batch_cook() -> str:
        """Reads the active batch cook CSV artifact."""
        rows = get_batch_cook_csv(data_dir)
        if not rows:
            return "No batch cook instructions found."
        lines = ["| Dish | Main Protein | Meals |", "|---|---|---|"]
        for r in rows:
            lines.append(f"| {r.get('Dish')} | {r.get('Main_Protein')} | {r.get('Meals')} |")
        return "\n".join(lines)

    def tool_update_batch_cook(dishes: list[dict]) -> str:
        """Updates the active batch cook CSV artifact.
        
        Args:
            dishes: List of batch-cooked dish dicts:
                    [{'Dish': 'Thịt Kho Tàu', 'Main_Protein': '1000g Pork Belly', 'Meals': 3}]
                    - 'Dish': The dish name (just the name, no dish weight required).
                    - 'Main_Protein': The main protein and amount in grams or kg (e.g. '1000g Pork Belly', '1kg Chicken Thighs'). This is the ONLY ingredient to list.
                    - 'Meals': How many meals this batch cook covers (e.g. 3).
        """
        res = update_batch_cook_csv(data_dir, dishes)
        return res.get("message", "Batch cook instructions updated.")

    def tool_check_meal_plan(
        target_calories: Optional[float] = None,
        target_p: Optional[float] = None,
        target_c: Optional[float] = None,
        target_f: Optional[float] = None
    ) -> str:
        """Checks the weekly meal plan sums against target calories and macros (P/C/F).
        
        Verifies that weekly total planned calories and P/C/F approximate the nutritional
        goals, including carried deficits or surpluses from last week recorded in memory.
        Returns [ACCEPTED] if approved, or [NEEDS FIXING] with discrepancies to fix.
        
        Args:
            target_calories: Optional explicit weekly calorie goal. If omitted, derived from memory.
            target_p: Optional explicit weekly protein goal (g). If omitted, derived from memory.
            target_c: Optional explicit weekly carb goal (g). If omitted, derived from memory.
            target_f: Optional explicit weekly fat goal (g). If omitted, derived from memory.
        """
        res = check_meal_plan_csv(
            data_dir,
            target_weekly_calories=target_calories,
            target_weekly_p=target_p,
            target_weekly_c=target_c,
            target_weekly_f=target_f
        )
        return res["message"]

    return [
        tool_save_memory_note,
        tool_get_meal_plan,
        tool_update_meal_plan,
        tool_get_grocery_list,
        tool_update_grocery_list,
        tool_get_batch_cook,
        tool_update_batch_cook,
        tool_check_meal_plan,
    ]

def get_root_agent(data_dir: str = "data"):
    """Instantiates the Google ADK Agent for the Meal Planner."""
    try:
        from google.adk import Agent
    except ImportError:
        return None

    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    user_tz = "Europe/Brussels"
    tools = get_agent_tools(data_dir)
    sys_instruction = build_system_instruction(user_tz, data_dir=data_dir)

    return Agent(
        name="meal_planner",
        model=model_name,
        description="AI Meal & Grocery Planner Agent with multimodal receipt and meal analysis.",
        instruction=sys_instruction,
        tools=tools,
    )

root_agent = get_root_agent("data")
