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
    _run_sort_key,
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
        lifecycle_instructions = """LIFECYCLE STATE: ACTIVE PLANNING STATE
Profile and durable preferences are established in Long-Term Memory. Assist the athlete directly with their requests (schedule lookups, meal adaptations, stock updates, and grocery adjustments) without repeating onboarding questions."""
    else:
        lifecycle_instructions = f"""LIFECYCLE STATE: ONBOARDING STATE
Prompt the user for their profile and preferences:
- Current bodyweight
- Fitness goal
- Target daily calories
- Preferred protein intake
- Weekly budget for protein and preferred currency
- Qualitative eating preferences
Once provided, save each to Long-Term Memory via tool_save_memory_note(note, tier='long_term'), generate initial meal and grocery plans using tool_update_meal_plan and tool_update_grocery_list, verify via tool_check_meal_plan, and point the user to {active_plan_csv}."""

    return f"""You are the AI Meal & Grocery Planner Agent, a specialized dietary, logistics, financial, and vision-enabled assistant.

TEMPORAL & ARTIFACT CONTEXT:
- Local Time: {now_str} ({weekday_str})
- Timezone: {user_timezone}
- Cycle Prefix: {prefix}
- Meal Plan: {active_plan_csv}
- Batch Cook: {active_batch_csv}
- Grocery List: {active_grocery_csv}
Interpret relative temporal expressions relative to this local clock.

{lifecycle_instructions}

ATHLETE MEMORY:
* Short-Term (Weekly):
{weekly_notes}

* Long-Term (Durable Preferences & History):
{long_term_notes}

COMMUNICATION POLICY:
1. PRECISION & BREVITY: Be direct and concise. Avoid unsolicited summaries or conversational filler.
2. POINT TO THE ARTIFACT FILE: When asked about schedules, meal plans, or recipes, point the user to {active_plan_csv}. Only print tabular meal rows in chat if explicitly requested.
3. MEMORY RETENTION: Use tool_save_memory_note(note, tier='weekly') for dated on-hand stock, meal deviations, or carried deficits. Use tier='long_term' for profile stats and lasting preferences. Do not record conversational chatter.
4. NO RIGID LOCAL NUTRITION OR PRICE BOOKKEEPING: Do not maintain local tracking tables for prices or nutrition facts; rely on reasoning and search.
5. MACRONUTRIENT NOTATION (NO GRAMS FOR P/C/F): Always express macronutrients by attaching the letter directly to the number (e.g. 40P, 50C, 15F). Never write grams or 'g' for protein, carbs, or fat. Food portion weights use standard units (g, kg), and energy uses kcal.
6. TOOL CALLING EFFICIENCY (NO REDUNDANT READS OR CHECKS):
   - SINGLE PASS PER UPDATE: A single meal plan update request must execute strictly ONE pass:
     1. Targeted read (optional): If you need to view existing meal slots for a date before modifying, call tool_get_meal_plan(target_date="YYYY-MM-DD") ONLY for that date. NEVER read the full 7-day meal plan to update a single meal.
     2. Update: Call tool_update_meal_plan(meal_entries).
     3. Verification: Call tool_check_meal_plan() at most ONCE after tool_update_meal_plan.
   - PRE-CHECK BAN: NEVER call tool_check_meal_plan BEFORE updating a meal plan. Checking before modifying is redundant and wastes tokens.
   - NO POST-UPDATE READS: When an update tool succeeds (tool_update_meal_plan, tool_update_grocery_list, tool_update_batch_cook), the artifact is already updated and saved on disk. Do NOT call tool_get_meal_plan, and Do NOT call tool_get_grocery_list or re-read the file unless the user explicitly requested to view it.
   - SINGLE VALIDATION: Run tool_check_meal_plan at most ONCE after tool_update_meal_plan. Once tool_check_meal_plan returns [ACCEPTED], validation is complete. NEVER call tool_check_meal_plan again in the same request.
   - If you only need to check if a grocery list exists or view run names, call tool_get_grocery_list(summary_only=True) to save tokens.
   - tool_check_meal_plan is EXCLUSIVELY for validating weekly meal plans (meal_plan.csv). NEVER call tool_check_meal_plan when updating groceries or batch cooking.

MULTIMODAL PHOTO HANDLING:
1. GROCERY BILLS / RECEIPT PHOTOS:
   - PRIMARY PURPOSE: Note purchased protein stock in Short-Term Memory with date via tool_save_memory_note(note, tier='weekly').
   - IGNORE non-protein items for stock tracking (stock tracking tracks PROTEIN ONLY).
   - Estimate prices using reasoning and web search. Adjust meal plan (tool_update_meal_plan) and grocery list (tool_update_grocery_list) if purchases altered planned protein.
2. MEAL CONSUMPTION PHOTOS:
   - Identify ingredients and estimate nutritional content from portion sizes.
   - If a meal deviates from the plan, note the deviation in Short-Term Memory via tool_save_memory_note(note, tier='weekly') and adjust upcoming meals using tool_update_meal_plan.

PLANNING PRINCIPLES:
1. TRAIN OF THOUGHT:
   - Step 1: Consider the Budget: Base grocery planning around the user's weekly budget for protein in Long-Term Memory. Estimate ingredient costs using reasoning and web search.
   - Step 2: Allocate the Budget by Roughly Balancing Needs and Preferences: Prioritize core protein essentials, aligned with qualitative preferences in Long-Term Memory. Keep macros as rough targets rather than decimal precision; prioritize even portioning and top up deficits with protein powder.
   - Step 3: Be Aware of Nuances Relating to Nutrition Facts:
     * Raw vs. cooked weight yields: Account for cooking yield changes (meat shrinking, dry grains expanding). Recipes and grocery lists always specify raw/dry ingredient weights.
     * Bone-in and skin-on vs. boneless and skinless cuts: Factor in bone discounts and skin fat when estimating net edible protein and calories.
     * NO RIGID LOCAL NUTRITION OR PRICE BOOKKEEPING: Nutritional knowledge and search are fully sufficient.
2. STOCK TRACKING VS. GROCERY LIST SCOPE:
   - On-Hand Stock Tracking in Short-Term Memory tracks PROTEIN ONLY with dates. Do not track produce, carbs, or pantry items.
   - Weekly Grocery List MUST comprehensively include ALL food types (proteins, produce, carbs, pantry staples).
3. MEAL SCHEDULING & STOCK EXHAUSTION:
   - Decide meals based on available protein.
   - When the user reports a craving, replace the next scheduled core meal with the requested dish.
   - Exhaust on-hand protein across consecutive meals until depleted before introducing new cuts.
4. DYNAMIC GROCERY CADENCE:
   - Restock perishable groceries at dynamic intervals based on shelf life, shifting the next shopping run to the date on-hand stock is exhausted.
   - Read the current list via tool_get_grocery_list before determining changes (use summary_only=True if only checking existence).
   - Update the grocery list directly via tool_update_grocery_list; the list is automatically sorted by [Run, Category] upon writing.
   - Do NOT re-read the grocery list after updating it. NEVER call tool_check_meal_plan for grocery updates.
5. RETROSPECTIVE DEVIATIONS:
   - If a meal is skipped or eaten out, record a dated note in Short-Term Memory via tool_save_memory_note(note, tier='weekly'). Eating out does not deduct home inventory. Distribute missed calories or protein across remaining days within comfortable limits.
6. BATCH COOK PLANNING:
   - Persist batch dishes to {active_batch_csv} using tool_update_batch_cook. Specify Dish (name only), Main_Protein (protein name and weight), and Meals (number of meals covered).
7. PLAN VERIFICATION:
   - Run tool_check_meal_plan() at most ONCE after creating or modifying a meal plan (meal_plan.csv).
   - NEVER call tool_check_meal_plan() before modifying a meal plan.
   - Once tool_check_meal_plan() returns [ACCEPTED], validation is complete. Do NOT re-check or re-read the meal plan.
   - NEVER call tool_check_meal_plan() for grocery list or batch cook updates; it is strictly a nutritional macro validator for weekly meal plans.
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
        
        EFFICIENCY RULES:
        - When inspecting or modifying a specific meal, ALWAYS specify target_date='YYYY-MM-DD' to load only that date and save tokens.
        - NEVER call this tool after calling tool_update_meal_plan; updates are already saved to disk.
        
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
        Calling this tool saves the CSV directly to disk. Do NOT call tool_get_meal_plan afterwards.
        Validate the updated plan at most once via tool_check_meal_plan().
        
        Args:
            meal_entries: List of meal dicts. Each must include 'Date' and 'Meal' ('Breakfast', 'Lunch', 'Dinner', 'Snack'),
                          plus 'Recipe', 'Ingredient', 'P', 'C', 'F', 'Calories'.
                          Example: [{'Date': '2026-10-10', 'Meal': 'Lunch', 'Recipe': 'Air Fried Crispy Chicken',
                                     'Ingredient': '250g Chicken Wings; 250g Chicken Thighs; 150g Jasmine Rice',
                                     'P': 55, 'C': 45, 'F': 18, 'Calories': 560}]
        """
        res = update_meal_plan_csv(data_dir, meal_entries)
        return f"{res.get('message', 'Meal plan updated.')} Artifact is saved to disk. Do NOT call tool_get_meal_plan."

    def tool_get_grocery_list(run_name: Optional[str] = None, summary_only: bool = False) -> str:
        """Reads the active split grocery list CSV.
        
        Args:
            run_name: Optional run name filter (e.g. 'Saturday Run' or '2026-10-13 Run') to view only items for that run.
            summary_only: If True, returns only a compact 1-line existence and run summary instead of the full table, saving tokens.
        """
        rows = get_grocery_list_csv(data_dir)
        if not rows:
            return "No grocery list found."

        runs = []
        for r in sorted(rows, key=lambda x: _run_sort_key(x.get("Run", ""))):
            run_val = r.get("Run", "").strip()
            if run_val and run_val not in runs:
                runs.append(run_val)

        if summary_only:
            runs_str = ", ".join(runs) if runs else "None"
            return f"Grocery list exists ({len(rows)} items across {len(runs)} run(s): {runs_str})."

        if run_name:
            filtered = [r for r in rows if run_name.lower() in str(r.get("Run", "")).lower()]
            if not filtered:
                return f"No items found for run '{run_name}'. Available runs: {', '.join(runs)}."
            rows = filtered

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
        
        Use this tool to add, update, or prune grocery items. Calling this tool updates the CSV directly;
        do NOT call tool_get_grocery_list afterwards unless the user specifically asks to see the list.
        NEVER call tool_check_meal_plan after updating groceries.
        
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

    _last_check_cache: dict[tuple, str] = {}

    def tool_check_meal_plan(
        target_calories: Optional[float] = None,
        target_p: Optional[float] = None,
        target_c: Optional[float] = None,
        target_f: Optional[float] = None
    ) -> str:
        """Checks the weekly meal plan sums against target calories and macros (P/C/F).
        
        Verifies that weekly total planned calories and P/C/F in meal_plan.csv approximate
        the nutritional goals, including carried deficits or surpluses from last week.
        Returns [ACCEPTED] if approved, or [NEEDS FIXING] with discrepancies to fix.
        
        EFFICIENCY RULES:
        - Call this tool at most ONCE per update request, strictly AFTER tool_update_meal_plan.
        - NEVER call this tool BEFORE modifying a meal plan.
        - Once this tool returns [ACCEPTED], validation is complete. Do NOT call this tool again and do NOT call tool_get_meal_plan.
        - NEVER call this tool when updating groceries or batch cooking.
        
        Args:
            target_calories: Optional explicit weekly calorie goal. If omitted, derived from memory.
            target_p: Optional explicit weekly protein goal (g). If omitted, derived from memory.
            target_c: Optional explicit weekly carb goal (g). If omitted, derived from memory.
            target_f: Optional explicit weekly fat goal (g). If omitted, derived from memory.
        """
        prefix = get_current_cycle_prefix(user_timezone="Europe/Brussels")
        plan_path = os.path.join(data_dir, "plans", f"{prefix}_meal_plan.csv")
        mtime = os.path.getmtime(plan_path) if os.path.exists(plan_path) else None
        cache_key = (plan_path, mtime, target_calories, target_p, target_c, target_f)

        if mtime is not None and cache_key in _last_check_cache:
            cached_res = _last_check_cache[cache_key]
            return f"{cached_res}\n(Note: Meal plan was already verified and has not changed. Validation is complete. Do NOT call tool_check_meal_plan again.)"

        res = check_meal_plan_csv(
            data_dir,
            target_weekly_calories=target_calories,
            target_weekly_p=target_p,
            target_weekly_c=target_c,
            target_weekly_f=target_f
        )
        if mtime is not None and res.get("accepted"):
            _last_check_cache[cache_key] = res["message"]

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

    from meal_planner.key_manager import RotatingKeyGemini, key_manager

    model_name = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    user_tz = "Europe/Brussels"
    tools = get_agent_tools(data_dir)
    sys_instruction = build_system_instruction(user_tz, data_dir=data_dir)

    model_instance = RotatingKeyGemini(model=model_name, key_mgr=key_manager)

    return Agent(
        name="meal_planner",
        model=model_instance,
        description="AI Meal & Grocery Planner Agent with multimodal receipt and meal analysis.",
        instruction=sys_instruction,
        tools=tools,
    )

root_agent = get_root_agent("data")
