import os
import sys
from datetime import datetime
from meal_planner.agent import get_agent_tools, build_system_instruction
from meal_planner.tools.onboarding import load_user_profile, init_user_profile, resolve_timezone
from meal_planner.tools.memory import MemoryManager
from meal_planner.tools.meal_generator import ensure_weekly_plan_artifacts, get_current_cycle_prefix

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def get_model_name() -> str:
    """Returns the Gemini model to use, defaulting to gemini-3.8-flash."""
    return os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

def ensure_api_key(input_fn=input) -> str:
    """Checks for GEMINI_API_KEY or GOOGLE_API_KEY, prompts the user if missing, and optionally persists to .env."""
    key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
    if key:
        os.environ["GEMINI_API_KEY"] = key
        os.environ["GOOGLE_API_KEY"] = key
        return key

    print("\n[*] No GEMINI_API_KEY detected in environment or .env file.")
    print("A Gemini API key is needed for live conversational AI and dynamic reasoning.")
    try:
        entered = input_fn("Enter your Gemini API key (or press Enter to skip): ").strip()
    except (KeyboardInterrupt, EOFError):
        return ""

    if not entered:
        print("Skipping API key setup. Running in local deterministic mode.")
        return ""

    os.environ["GEMINI_API_KEY"] = entered
    os.environ["GOOGLE_API_KEY"] = entered
    try:
        save = input_fn("Save this key to .env for future sessions? (y/N): ").strip().lower()
        if save in ["y", "yes"]:
            env_path = ".env"
            with open(env_path, "a", encoding="utf-8") as f:
                f.write(f"\nGEMINI_API_KEY={entered}\nGOOGLE_API_KEY={entered}\n")
            print("[OK] GEMINI_API_KEY and GOOGLE_API_KEY saved to .env file.")
    except (KeyboardInterrupt, EOFError):
        pass

    return entered

def run_interactive_cli(data_dir: str = "data") -> None:
    """Runs the interactive Meal Planner agent terminal session."""
    print("=" * 70)
    print("  === AI Meal & Grocery Planner Agent (Gemini ADK) ===")
    print("=" * 70)

    # 1. Check or perform onboarding
    profile = load_user_profile(data_dir)
    tools = get_agent_tools(data_dir)
    tools_map = {t.__name__: t for t in tools}

    if not profile:
        print("\n[Welcome] No athlete profile found. Let's do a quick onboarding setup.")
        try:
            tz_input = input("Enter your timezone (e.g. Europe/Brussels, UTC+2, America/New_York) [Europe/Brussels]: ").strip()
            tz_name = tz_input if tz_input else "Europe/Brussels"

            bw_input = input("Enter your current bodyweight in kg [65]: ").strip()
            bw = float(bw_input) if bw_input else 65.0

            goal = input("Enter your goal state (lean_bulk / cut / maintenance) [lean_bulk]: ").strip()
            goal = goal if goal else "lean_bulk"

            cal_input = input("Enter target daily calories (or press enter for default ~2550) [2550]: ").strip()
            target_kcal = float(cal_input) if cal_input else 2550.0

            prot_mult = input("Enter protein multiplier g/kg [2.3]: ").strip()
            p_mult = float(prot_mult) if prot_mult else 2.3

            fat_mult = input("Enter fat multiplier g/kg [1.0]: ").strip()
            f_mult = float(fat_mult) if fat_mult else 1.0

            print("\n[Setup] Initializing your profile and local bookkeeping files...")
            init_msg = tools_map["tool_onboard_user"](tz_name, bw, goal, target_kcal, p_mult, f_mult)
            print(f"[OK] {init_msg}")

            print("\n[Plan] Generating your initial weekly meal plan and split grocery list...")
            plan_msg = tools_map["tool_generate_meal_plan"]()
            print(f"[OK] {plan_msg}")

            profile = load_user_profile(data_dir)
        except (KeyboardInterrupt, EOFError):
            print("\nOnboarding aborted.")
            return

    user_tz = profile.timezone if profile else "Europe/Brussels"

    # 2. Blank-slate memory hydration & weekly plan check (only relevant files)
    print("\n[*] Hydrating relevant context files from blank slate...")
    mem_mgr = MemoryManager(data_dir)
    records, total_ms = mem_mgr.hydrate(user_timezone=user_tz)
    for label, path, elapsed_ms in records:
        print(f"  - [Loaded] {label}: {path} ({elapsed_ms:.2f} ms)")
    print(f"[OK] Relevant context hydrated in {total_ms:.2f} ms.")

    if profile:
        plan_path, grocery_path, newly_created = ensure_weekly_plan_artifacts(profile, data_dir)
        if newly_created:
            print(f"[*] Generated isolated weekly meal plan for this cycle: {plan_path}")
        else:
            print(f"[*] Active weekly meal plan artifact verified: {plan_path}")

    sys_instruction = build_system_instruction(user_tz, data_dir=data_dir)

    # 3. Check and prompt for API key if missing
    api_key = ensure_api_key()
    if not api_key:
        print("\nRunning in local deterministic mode. Supported commands:")
        print("  /plan        - Re-generate and export meal plan & grocery CSVs")
        print("  /groceries   - View current split grocery list")
        print("  /analytics   - View protein spend & adherence analytics")
        print("  /memory      - View stored short-term and long-term notes")
        print("  /exit        - Exit the agent\n")

    # Set up Gemini client if API key and library are present
    client = None
    chat = None
    model_name = get_model_name()
    try:
        from google import genai
        from google.genai import types
        if api_key:
            client = genai.Client(api_key=api_key)
            # Create chat session with tools and system instruction
            config = types.GenerateContentConfig(
                system_instruction=sys_instruction,
                tools=tools,
                temperature=0.2
            )
            chat = client.chats.create(model=model_name, config=config)
            print(f"[AI] Gemini Agent ({model_name}) is active and ready!")
    except Exception as e:
        print(f"Note: Gemini client initialization ({e}). Local fallback mode active.")

    print(f"\nTimezone: {user_tz} | Bodyweight: {profile.bodyweight_kg}kg | Goal: {profile.goal_state}")
    print("You can chat naturally (e.g. 'I drank a double shake instead of Thursday dinner', 'Pork was €15/kg so I bought chicken').")
    print("Type /exit to quit.\n")

    while True:
        try:
            user_input = input("You > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["/exit", "exit", "quit", ":q"]:
                print("Goodbye! Train hard.")
                break

            # Local shortcut commands
            if user_input == "/plan":
                print(tools_map["tool_generate_meal_plan"]())
                continue
            elif user_input == "/groceries":
                print(tools_map["tool_view_grocery_list"]())
                continue
            elif user_input == "/analytics":
                print(tools_map["tool_get_analytics"]())
                continue
            elif user_input == "/memory":
                ctx = mem_mgr.get_context()
                print("\n[Weekly Memory]")
                if ctx["weekly"]:
                    for n in ctx["weekly"]:
                        print(f"  - {n}")
                else:
                    print("  (Empty)")
                print("\n[Long-term Memory]")
                if ctx["long_term"]:
                    for n in ctx["long_term"]:
                        print(f"  - {n}")
                else:
                    print("  (Empty)")
                print()
                continue

            # Send to Gemini Chat session if active
            handled_by_gemini = False
            if chat:
                try:
                    response = chat.send_message(user_input)
                    print(f"\nAgent > {response.text}\n")
                    handled_by_gemini = True
                except Exception as e:
                    print(f"\n[!] Gemini API error ({e}). Falling back to local execution.\n")

            if not handled_by_gemini:
                # Local fallback parser for key actions
                lower = user_input.lower()
                if "schedule" in lower or "what is my schedule" in lower or ("meal" in lower and "plan" in lower):
                    prefix = get_current_cycle_prefix(user_tz)
                    active_plan = os.path.join(data_dir, "plans", f"{prefix}_meal_plan.csv")
                    print(f"\nAgent > Your weekly meal plan is stored at: {active_plan}\n(Ask me explicitly to 'print the plan' if you wish to see all rows in chat).\n")
                elif "print the plan" in lower or "show the plan" in lower:
                    print(f"\nAgent > {tools_map['tool_generate_meal_plan']()}\n")
                elif "shake" in lower or "missed" in lower or "skip" in lower:
                    res = tools_map["tool_report_meal_deviation"](
                        "Thursday", "dinner", "Double Whey Shake", 50.0, 300.0
                    )
                    print(f"\nAgent > {res}\n")
                elif "substitute" in lower or "bought extra chicken" in lower or "pork" in lower:
                    res = tools_map["tool_substitute_ingredient"]("pork_shoulder", "chicken_breast", 9.50)
                    print(f"\nAgent > {res}\n")
                elif "price" in lower:
                    res = tools_map["tool_log_price_update"]("chicken_breast", 9.50)
                    print(f"\nAgent > {res}\n")
                elif "analytic" in lower or "spend" in lower:
                    print(f"\nAgent > {tools_map['tool_get_analytics']()}\n")
                else:
                    print("\nAgent > I received your input. Set GEMINI_API_KEY to enable full live LLM reasoning for any natural language input.\n")

        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break

def serve_adk_playground(
    port: int = 8080,
    host: str = "127.0.0.1",
    data_dir: str = "data"
) -> None:
    """Starts the Google ADK playground web server for interactive multimodal chat."""
    print("=" * 70)
    print("  === AI Meal & Grocery Planner Agent (Google ADK Playground) ===")
    print("=" * 70)

    # 1. API key verification
    ensure_api_key()

    # 2. Check profile or onboard
    profile = load_user_profile(data_dir)
    tools = get_agent_tools(data_dir)
    tools_map = {t.__name__: t for t in tools}

    if not profile:
        print("\n[Welcome] No athlete profile found. Let's do a quick onboarding setup.")
        try:
            tz_input = input("Enter your timezone (e.g. Europe/Brussels, UTC+2, America/New_York) [Europe/Brussels]: ").strip()
            tz_name = tz_input if tz_input else "Europe/Brussels"

            bw_input = input("Enter your current bodyweight in kg [65]: ").strip()
            bw = float(bw_input) if bw_input else 65.0

            goal = input("Enter your goal state (lean_bulk / cut / maintenance) [lean_bulk]: ").strip()
            goal = goal if goal else "lean_bulk"

            cal_input = input("Enter target daily calories (or press enter for default ~2550) [2550]: ").strip()
            target_kcal = float(cal_input) if cal_input else 2550.0

            prot_mult = input("Enter protein multiplier g/kg [2.3]: ").strip()
            p_mult = float(prot_mult) if prot_mult else 2.3

            fat_mult = input("Enter fat multiplier g/kg [1.0]: ").strip()
            f_mult = float(fat_mult) if fat_mult else 1.0

            print("\n[Setup] Initializing your profile and local bookkeeping files...")
            init_msg = tools_map["tool_onboard_user"](tz_name, bw, goal, target_kcal, p_mult, f_mult)
            print(f"[OK] {init_msg}")

            print("\n[Plan] Generating your initial weekly meal plan and split grocery list...")
            plan_msg = tools_map["tool_generate_meal_plan"]()
            print(f"[OK] {plan_msg}")

            profile = load_user_profile(data_dir)
        except (KeyboardInterrupt, EOFError):
            print("\nOnboarding aborted.")
            return

    user_tz = profile.timezone if profile else "Europe/Brussels"

    # 3. Blank-slate memory hydration (only relevant files)
    print("\n[*] Hydrating relevant context files from blank slate...")
    mem_mgr = MemoryManager(data_dir)
    records, total_ms = mem_mgr.hydrate(user_timezone=user_tz)
    for label, path, elapsed_ms in records:
        print(f"  - [Loaded] {label}: {path} ({elapsed_ms:.2f} ms)")
    print(f"[OK] Relevant context hydrated in {total_ms:.2f} ms.")

    if profile:
        plan_path, grocery_path, newly_created = ensure_weekly_plan_artifacts(profile, data_dir)
        if newly_created:
            print(f"[*] Generated isolated weekly meal plan for this cycle: {plan_path}")
        else:
            print(f"[*] Active weekly meal plan artifact verified: {plan_path}")

    url = f"http://{host}:{port}/dev-ui/?app=meal_planner"
    print("\n" + "=" * 70)
    print(f"[*] Launching Google ADK Playground at: {url}")
    print("    - Chat with your Meal Planner agent in the visual playground")
    print("    - Upload photos of grocery bills/receipts to log prices or substitutions")
    print("    - Upload photos of meals to estimate calories/protein and adapt your plan")
    print("=" * 70 + "\n")

    import subprocess
    cmd = [
        sys.executable, "-m", "google.adk.cli", "web",
        "--host", host,
        "--port", str(port),
        "."
    ]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nADK Playground server shut down.")

if __name__ == "__main__":
    serve_adk_playground()
