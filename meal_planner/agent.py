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

    plan_rows = get_meal_plan_csv(data_dir, prefix=prefix)
    if plan_rows:
        lines = [
            "| Date | Meal | Recipe | Ingredients | P | C | F | Kcal |",
            "|---|---|---|---|---|---|---|---|"
        ]
        for r in plan_rows:
            lines.append(
                f"| {r.get('Date')} | {r.get('Meal')} | {r.get('Recipe')} | {r.get('Ingredient')} | "
                f"{r.get('P')} | {r.get('C')} | {r.get('F')} | {r.get('Calories')} |"
            )
        weekly_plan_context = "\n".join(lines)
    else:
        weekly_plan_context = "  (No weekly meal plan generated yet. Generate the baseline plan using tool_update_plans.)"

    batch_rows = get_batch_cook_csv(data_dir, prefix=prefix)
    if batch_rows:
        lines = [
            "| Dish | Main Protein | Meals |",
            "|---|---|---|"
        ]
        for r in batch_rows:
            lines.append(f"| {r.get('Dish')} | {r.get('Main_Protein')} | {r.get('Meals')} |")
        batch_cook_context = "\n".join(lines)
    else:
        batch_cook_context = "  (No batch cook instructions generated yet.)"

    grocery_rows = get_grocery_list_csv(data_dir, prefix=prefix)
    if grocery_rows:
        lines = [
            "| Run | Category | Item | Quantity_g | Estimated_Price_EUR |",
            "|---|---|---|---|---|"
        ]
        for r in sorted(grocery_rows, key=lambda x: _run_sort_key(x.get("Run", ""))):
            lines.append(
                f"| {r.get('Run')} | {r.get('Category')} | {r.get('Item')} | "
                f"{r.get('Quantity_g')} | {r.get('Estimated_Price_EUR')} |"
            )
        grocery_list_context = "\n".join(lines)
    else:
        grocery_list_context = "  (No grocery list generated yet.)"

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
Once provided, save each to Long-Term Memory and generate initial meal, batch cook, and grocery plans using tool_update_plans, and point the user to {active_plan_csv}."""

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

ATHLETE MEMORY & ACTIVE CONTEXT:
* Short-Term (Weekly):
{weekly_notes}

* Long-Term (Durable Preferences & History):
{long_term_notes}

* Active Weekly Meal Plan (Full Context):
{weekly_plan_context}

* Active Batch Cook Instructions (Full Context):
{batch_cook_context}

* Active Grocery List (Full Context):
{grocery_list_context}

COMMUNICATION POLICY:
1. PRECISION & BREVITY: Be direct and concise. Avoid unsolicited summaries or conversational filler.
2. POINT TO THE ARTIFACT FILE: When asked about schedules, meal plans, or recipes, point the user to {active_plan_csv}. Only print tabular meal rows in chat if explicitly requested.
3. MEMORY RETENTION: Use tool_update_plans(short_term_notes=[...]) or tool_save_memory_note(note, tier='weekly') for dated on-hand stock, meal deviations, or carried deficits. Use long_term_notes for profile stats and lasting preferences. Do not record conversational chatter.
4. NO RIGID LOCAL NUTRITION OR PRICE BOOKKEEPING: Do not maintain local tracking tables for prices or nutrition facts; rely on reasoning and search.
5. MACRONUTRIENT NOTATION (NO GRAMS FOR P/C/F): Always express macronutrients by attaching the letter directly to the number (e.g. 40P, 50C, 15F). Never write grams or 'g' for protein, carbs, or fat. Food portion weights use standard units (g, kg), and energy uses kcal.
6. TOOL CALLING EFFICIENCY (SINGLE CONSOLIDATED UPDATE TOOL):
   - FULL SHORT-TERM CONTEXT INJECTED: The active weekly meal plan, batch cook instructions, and grocery list are already fully provided in your context above under Active Context. You do NOT need to call any tool to inspect or read plans.
   - UNIFIED SINGLE CALL: Use tool_update_plans to modify, replace, or add entries across ANY plan and/or memory (short-term & long-term). When a request impacts memory and plans (e.g. reporting on-hand protein stock, craving adjustments, skipped meals, batch cooking), pass short_term_notes, meal_entries, batch_cook_entries, and/or grocery_entries together in strictly ONE single tool call.
   - AUTOMATIC PLAN VALIDATION: tool_update_plans automatically executes nutritional verification upon writing meal entries and returns the validation report. You do NOT need to call tool_check_meal_plan yourself!
   - NO PRE-CHECKS: NEVER call tool_check_meal_plan before updating plans.
   - NO POST-UPDATE READS: When tool_update_plans succeeds, the artifacts are already updated and saved on disk. Do NOT re-read files unless the user explicitly requested to view them.

MULTIMODAL PHOTO HANDLING:
1. GROCERY BILLS / RECEIPT PHOTOS:
   - PRIMARY PURPOSE: Note purchased protein stock in Short-Term Memory with date and adjust plans via tool_update_plans(short_term_notes=[...], meal_entries=[...], grocery_entries=[...]) in a single call.
   - IGNORE non-protein items for stock tracking (stock tracking tracks PROTEIN ONLY).
   - Estimate prices using reasoning and web search.
2. MEAL CONSUMPTION PHOTOS:
   - Identify ingredients and estimate nutritional content from portion sizes.
   - If a meal deviates from the plan, record the deviation in Short-Term Memory and adjust upcoming meals via tool_update_plans(short_term_notes=[...], meal_entries=[...]) in a single call.

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
   - Update grocery runs via tool_update_plans(grocery_entries=[...], grocery_mode='merge'/'replace'). The list is automatically sorted by [Run, Category] upon writing.
5. RETROSPECTIVE DEVIATIONS:
   - If a meal is skipped or eaten out, record a dated note in Short-Term Memory and adjust upcoming meal slots via tool_update_plans(short_term_notes=[...], meal_entries=[...]). Eating out does not deduct home inventory. Distribute missed calories or protein across remaining days within comfortable limits.
6. BATCH COOK PLANNING:
   - Persist batch dishes to {active_batch_csv} via tool_update_plans(batch_cook_entries=[...]). Specify Dish (name only), Main_Protein (protein name and weight), and Meals (number of meals covered).
7. PLAN VERIFICATION:
   - Nutritional validation runs automatically inside tool_update_plans whenever meal_entries are modified.
   - You do NOT need to call tool_check_meal_plan manually after updating plans.
   - NEVER call tool_check_meal_plan before modifying a meal plan.
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

    def tool_update_plans(
        meal_entries: Optional[list[dict]] = None,
        batch_cook_entries: Optional[list[dict]] = None,
        grocery_entries: Optional[list[dict]] = None,
        grocery_mode: str = "merge",
        short_term_notes: Optional[list[str]] = None,
        long_term_notes: Optional[list[str]] = None,
        **kwargs
    ) -> str:
        """Consolidated artifact & memory management tool. Updates, replaces, or adds entries across meal plans, batch cooking, grocery lists, and short/long-term memories in a SINGLE call.
        
        Use this tool to persist planned dishes, craving substitutions, stock exhaustion meals, batch cooking dishes, grocery runs, and dated stock/preference notes.
        Calling this tool automatically saves artifacts and memory to disk and executes nutritional validation on updated meals.
        Do NOT call redundant read or check tools afterwards.
        
        Args:
            meal_entries: Optional list of meal dicts to update/add in the active weekly meal plan.
                          Each dict requires: 'Date' (YYYY-MM-DD), 'Meal' ('Breakfast', 'Lunch', 'Dinner', 'Snack'),
                          'Recipe', 'Ingredient', 'P', 'C', 'F', 'Calories'.
                          Example: [{'Date': '2026-10-10', 'Meal': 'Lunch', 'Recipe': 'Air Fried Crispy Chicken',
                                     'Ingredient': '250g Chicken Wings; 250g Chicken Thighs; 150g Jasmine Rice',
                                     'P': 55, 'C': 45, 'F': 18, 'Calories': 560}]
            batch_cook_entries: Optional list of batch cooking dish dicts to persist to batch cook instructions.
                                Each dict requires: 'Dish' (name only), 'Main_Protein' (protein name and raw weight, e.g. '1000g Pork Belly'),
                                'Meals' (number of meals covered, e.g. 3).
                                Example: [{'Dish': 'Thịt Kho Tàu', 'Main_Protein': '1000g Pork Belly', 'Meals': 3}]
            grocery_entries: Optional list of grocery item dicts to update, add, or prune in the grocery list.
                             Each dict requires: 'Run' (e.g. '2026-10-12 Dynamic Run'), 'Category' ('meat', 'produce', 'carbs', 'dairy', 'pantry', 'other'),
                             'Item', 'Quantity_g' (integer grams; <= 0 prunes the item), 'Estimated_Price_EUR'.
                             Example: [{'Run': '2026-10-12 Dynamic Run', 'Category': 'meat', 'Item': 'Chicken Breast', 'Quantity_g': 1000, 'Estimated_Price_EUR': 9.50}]
            grocery_mode: 'merge' (default) to update/add/prune specified grocery items, or 'replace' to overwrite the whole grocery list.
            short_term_notes: Optional list of strings (or single string) to record into short-term (weekly) memory (e.g. dated stock on hand, skipped meals, carried deficits).
            long_term_notes: Optional list of strings (or single string) to record into long-term memory (e.g. profile stats, durable preferences, goals).
        """
        if short_term_notes is None:
            if "weekly_notes" in kwargs:
                short_term_notes = kwargs["weekly_notes"]
            elif "weekly_note" in kwargs:
                short_term_notes = kwargs["weekly_note"]
            elif "short_term_note" in kwargs:
                short_term_notes = kwargs["short_term_note"]

        if long_term_notes is None:
            if "long_term_note" in kwargs:
                long_term_notes = kwargs["long_term_note"]

        if isinstance(short_term_notes, str):
            short_term_notes = [short_term_notes]
        if isinstance(long_term_notes, str):
            long_term_notes = [long_term_notes]

        if batch_cook_entries is None and "dishes" in kwargs:
            batch_cook_entries = kwargs["dishes"]
        if "plan_type" in kwargs and "entries" in kwargs:
            ptype = str(kwargs["plan_type"]).lower()
            if "meal" in ptype and meal_entries is None:
                meal_entries = kwargs["entries"]
            elif "batch" in ptype and batch_cook_entries is None:
                batch_cook_entries = kwargs["entries"]
            elif "groc" in ptype and grocery_entries is None:
                grocery_entries = kwargs["entries"]

        results = []
        mgr = MemoryManager(data_dir)

        if short_term_notes:
            saved_notes = []
            for n in short_term_notes:
                r = mgr.add_note(n, tier="weekly")
                if r.get("status") == "saved":
                    saved_notes.append(n)
            if saved_notes:
                results.append(f"Short-Term Memory: Saved {len(saved_notes)} note(s) ('{'; '.join(saved_notes)}').")

        if long_term_notes:
            saved_notes = []
            for n in long_term_notes:
                r = mgr.add_note(n, tier="long_term")
                if r.get("status") == "saved":
                    saved_notes.append(n)
            if saved_notes:
                results.append(f"Long-Term Memory: Saved {len(saved_notes)} note(s) ('{'; '.join(saved_notes)}').")

        if meal_entries:
            m_res = update_meal_plan_csv(data_dir, meal_entries)
            results.append(f"Meal Plan: {m_res.get('message', 'Meal plan updated.')}")
            check_res = check_meal_plan_csv(data_dir)
            check_msg = check_res.get("message", "")
            results.append(f"[AUTOMATIC PLAN VALIDATION]:\n{check_msg}")

        if batch_cook_entries:
            b_res = update_batch_cook_csv(data_dir, batch_cook_entries)
            results.append(f"Batch Cook: {b_res.get('message', 'Batch cook instructions updated.')}")

        if grocery_entries:
            g_res = update_grocery_list_csv(data_dir, grocery_entries, mode=grocery_mode)
            results.append(f"Grocery List: {g_res.get('message', 'Grocery list updated.')}")

        if not results:
            return (
                "No updates provided. The active meal plan, batch cook instructions, "
                "grocery list, and memories are already loaded in your context above."
            )

        return "\n\n".join(results) + "\n\nArtifacts and memory are saved to disk. Do NOT call redundant read or check tools."

    tool_update_plan = tool_update_plans
    tool_update_artifacts = tool_update_plans

    def tool_update_meal_plan(meal_entries: list[dict]) -> str:
        return tool_update_plans(meal_entries=meal_entries)

    def tool_update_grocery_list(grocery_entries: list[dict], mode: str = "merge") -> str:
        return tool_update_plans(grocery_entries=grocery_entries, grocery_mode=mode)

    def tool_update_batch_cook(dishes: list[dict]) -> str:
        return tool_update_plans(batch_cook_entries=dishes)

    def tool_get_meal_plan(target_date: Optional[str] = None) -> str:
        rows = get_meal_plan_csv(data_dir, target_date=target_date)
        if not rows:
            return "No meal plan found. Generate a baseline plan first."
        lines = ["| Date | Meal | Recipe | Ingredients | P | C | F | Kcal |", "|---|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r.get('Date')} | {r.get('Meal')} | {r.get('Recipe')} | {r.get('Ingredient')} | {r.get('P')} | {r.get('C')} | {r.get('F')} | {r.get('Calories')} |")
        return "\n".join(lines)

    def tool_get_grocery_list(run_name: Optional[str] = None, summary_only: bool = False) -> str:
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
        lines = ["| Run | Category | Item | Quantity_g | Estimated_Price_EUR |", "|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda x: _run_sort_key(x.get("Run", ""))):
            lines.append(f"| {r.get('Run')} | {r.get('Category')} | {r.get('Item')} | {r.get('Quantity_g')} | {r.get('Estimated_Price_EUR')} |")
        return "\n".join(lines)

    def tool_get_batch_cook() -> str:
        rows = get_batch_cook_csv(data_dir)
        if not rows:
            return "No batch cook instructions found."
        lines = ["| Dish | Main Protein | Meals |", "|---|---|---|"]
        for r in rows:
            lines.append(f"| {r.get('Dish')} | {r.get('Main_Protein')} | {r.get('Meals')} |")
        return "\n".join(lines)

    _last_check_cache: dict[tuple, str] = {}

    def tool_check_meal_plan(
        target_calories: Optional[float] = None,
        target_p: Optional[float] = None,
        target_c: Optional[float] = None,
        target_f: Optional[float] = None
    ) -> str:
        """Checks the weekly meal plan sums against target calories and macros (P/C/F).
        
        NOTE: tool_update_plans ALREADY runs nutritional validation automatically upon updating meal plans.
        You do NOT need to call this tool after updating a meal plan.
        
        EFFICIENCY RULES:
        - NEVER call this tool before modifying a meal plan.
        - NEVER call this tool after tool_update_plans (validation runs automatically).
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
        tool_update_plans,
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
