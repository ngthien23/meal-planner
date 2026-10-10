import os
import sys
import threading
import webbrowser
import subprocess
from datetime import datetime
from meal_planner.agent import get_agent_tools, build_system_instruction
from meal_planner.models import UserProfile
from meal_planner.tools.onboarding import load_user_profile, init_user_profile, resolve_timezone
from meal_planner.tools.memory import MemoryManager
from meal_planner.tools.meal_generator import ensure_weekly_plan_artifacts, get_current_cycle_prefix

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(REPO_ROOT, ".env")

try:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH)
except ImportError:
    pass

def resolve_data_dir(data_dir: str = "data") -> str:
    """Resolves data_dir: anchors relative paths to REPO_ROOT unless another custom path is specified."""
    if os.path.isabs(data_dir):
        return data_dir
    if data_dir == "data" or not os.path.exists(data_dir):
        return os.path.join(REPO_ROOT, data_dir)
    return os.path.abspath(data_dir)

def get_model_name() -> str:
    """Returns the Gemini model to use, defaulting to gemini-3.8-flash."""
    return os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

def _open_browser_delayed(url: str, delay: float = 1.5) -> None:
    """Opens the default web browser after a brief delay so the server can bind."""
    def _open():
        import time
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass
    t = threading.Thread(target=_open, daemon=True)
    t.start()

def ensure_api_key(input_fn=None) -> str:
    """Checks for GEMINI_API_KEY or GOOGLE_API_KEY, prompts the user if missing, and optionally persists to .env."""
    if input_fn is None:
        input_fn = input
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
            env_path = getattr(sys.modules[__name__], "ENV_PATH", ".env")
            with open(env_path, "a", encoding="utf-8") as f:
                f.write(f"\nGEMINI_API_KEY={entered}\nGOOGLE_API_KEY={entered}\n")
            print("[OK] GEMINI_API_KEY and GOOGLE_API_KEY saved to .env file.")
    except (KeyboardInterrupt, EOFError):
        pass

    return entered

def quick_setup_wizard(
    data_dir: str = "data",
    input_fn=None,
    force: bool = False
) -> UserProfile:
    """Interactive quick setup wizard for configuring API key, preferences, timezone, currency, etc.
    
    Default preferences (restrictions) are empty so new users start with a clean slate.
    """
    if input_fn is None:
        input_fn = input
    data_dir = resolve_data_dir(data_dir)
    profile = load_user_profile(data_dir)
    if profile is not None and not force:
        return profile

    print("\n" + "=" * 70)
    print("  === AI Meal & Grocery Planner Agent - Quick Setup Wizard ===")
    print("=" * 70)
    print("Welcome! Let's get your personalized meal planning system configured.")
    print("This setup initializes your API key, regional preferences, and baseline nutrition.")

    # 1. API key setup
    api_key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        print("\n--- 1. Gemini API Key ---")
        print("A free Gemini API key is needed for multimodal AI chat, reading grocery bills, and meal adjustments.")
        print("You can get a free key at: https://aistudio.google.com/app/apikey")
        try:
            entered_key = input_fn("Enter your Gemini API key (or press Enter to run offline): ").strip()
            if entered_key:
                os.environ["GEMINI_API_KEY"] = entered_key
                os.environ["GOOGLE_API_KEY"] = entered_key
                env_file = getattr(sys.modules[__name__], "ENV_PATH", ".env")
                with open(env_file, "a" if os.path.exists(env_file) else "w", encoding="utf-8") as f:
                    f.write(f"\nGEMINI_API_KEY={entered_key}\nGOOGLE_API_KEY={entered_key}\n")
                print("[OK] Saved API key to .env file.")
        except (KeyboardInterrupt, EOFError):
            pass

    # 2. Regional & Preferences: Timezone & Currency
    print("\n--- 2. Regional Preferences ---")
    default_tz = "UTC"
    try:
        local_tz = datetime.now().astimezone().tzinfo
        if hasattr(local_tz, "key") and local_tz.key:
            default_tz = local_tz.key
    except Exception:
        pass

    tz_prompt = f"Enter your timezone (e.g. Europe/Brussels, America/New_York, UTC, Asia/Ho_Chi_Minh) [{default_tz}]: "
    try:
        tz_in = input_fn(tz_prompt).strip()
    except (KeyboardInterrupt, EOFError):
        tz_in = ""
    tz_name = tz_in if tz_in else default_tz

    try:
        curr_in = input_fn("Enter your preferred currency code (EUR, USD, GBP, VND, CAD, AUD, JPY) [EUR]: ").strip().upper()
    except (KeyboardInterrupt, EOFError):
        curr_in = ""
    currency = curr_in if curr_in else "EUR"

    try:
        start_day_in = input_fn("Enter day that starts your weekly meal plan cycle (e.g. Monday, Saturday, Sunday) [Monday]: ").strip().capitalize()
    except (KeyboardInterrupt, EOFError):
        start_day_in = ""
    week_start_day = start_day_in if start_day_in else "Monday"

    try:
        weeks_in = input_fn("Enter number of weeks ahead to plan (retention window) [1]: ").strip()
        weeks_ahead = int(weeks_in) if weeks_in else 1
    except (KeyboardInterrupt, EOFError, ValueError):
        weeks_ahead = 1

    # 3. Bodyweight & Goal
    print("\n--- 3. Bodyweight & Fitness Goals ---")
    try:
        bw_in = input_fn("Enter your current bodyweight in kg [70]: ").strip()
        bw = float(bw_in) if bw_in else 70.0
    except (KeyboardInterrupt, EOFError, ValueError):
        bw = 70.0

    try:
        goal_in = input_fn("Enter your fitness goal (maintenance / lean_bulk / cut) [maintenance]: ").strip().lower()
        goal = goal_in if goal_in in ["maintenance", "lean_bulk", "cut"] else "maintenance"
    except (KeyboardInterrupt, EOFError):
        goal = "maintenance"

    # Auto estimate calories based on goal and weight
    if goal == "lean_bulk":
        est_kcal = round(bw * 37)
    elif goal == "cut":
        est_kcal = round(bw * 27)
    else:
        est_kcal = round(bw * 32)

    try:
        cal_in = input_fn(f"Enter target daily calories (press Enter for auto-calculation) [{est_kcal}]: ").strip()
        target_kcal = float(cal_in) if cal_in else float(est_kcal)
    except (KeyboardInterrupt, EOFError, ValueError):
        target_kcal = float(est_kcal)

    try:
        prot_in = input_fn("Enter protein multiplier in g/kg [2.0]: ").strip()
        p_mult = float(prot_in) if prot_in else 2.0
    except (KeyboardInterrupt, EOFError, ValueError):
        p_mult = 2.0

    try:
        fat_in = input_fn("Enter fat multiplier in g/kg [1.0]: ").strip()
        f_mult = float(fat_in) if fat_in else 1.0
    except (KeyboardInterrupt, EOFError, ValueError):
        f_mult = 1.0

    # 4. Dietary Restrictions (Default EMPTY)
    print("\n--- 4. Dietary Restrictions & Allergies ---")
    try:
        restr_in = input_fn("Enter dietary restrictions separated by commas (press Enter for NONE) []: ").strip()
        if restr_in:
            restrictions = [r.strip() for r in restr_in.split(",") if r.strip()]
        else:
            restrictions = []
    except (KeyboardInterrupt, EOFError):
        restrictions = []

    profile_data = {
        "timezone": tz_name,
        "bodyweight_kg": bw,
        "goal_state": goal,
        "target_calories": target_kcal,
        "protein_multiplier": p_mult,
        "fat_multiplier": f_mult,
        "restrictions": restrictions,
        "week_start_day": week_start_day,
        "weeks_ahead": weeks_ahead,
        "currency": currency,
        "texture_rules": {
            "breakfast": "soft_or_liquid",
            "lunch": "solid_batch",
            "dinner": "broth_or_soft"
        }
    }
    profile = init_user_profile(data_dir, profile_data)
    ensure_weekly_plan_artifacts(profile, data_dir)
    print("\n[OK] Setup complete! Clean profile and weekly meal plan generated.")
    return profile

def run_interactive_cli(data_dir: str = "data") -> None:
    """Runs the interactive Meal Planner agent terminal session."""
    print("=" * 70)
    print("  === AI Meal & Grocery Planner Agent (Gemini ADK) ===")
    print("=" * 70)

    data_dir = resolve_data_dir(data_dir)

    # 1. Check or perform onboarding
    profile = load_user_profile(data_dir)
    tools = get_agent_tools(data_dir)
    tools_map = {t.__name__: t for t in tools}

    if not profile:
        profile = quick_setup_wizard(data_dir=data_dir)
        if not profile:
            print("\nSetup aborted.")
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
    data_dir: str = "data",
    auto_open_browser: bool = True
) -> None:
    """Starts the Google ADK playground web server for interactive multimodal chat."""
    print("=" * 70)
    print("  === AI Meal & Grocery Planner Agent (Google ADK Playground) ===")
    print("=" * 70)

    data_dir = resolve_data_dir(data_dir)

    # 1. API key verification
    ensure_api_key()

    # 2. Check profile or onboard
    profile = load_user_profile(data_dir)
    if not profile:
        profile = quick_setup_wizard(data_dir=data_dir)
        if not profile:
            print("\nSetup aborted.")
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

    if auto_open_browser:
        _open_browser_delayed(url)

    cmd = [
        sys.executable, "-m", "google.adk.cli", "web",
        "--host", host,
        "--port", str(port),
        REPO_ROOT
    ]
    try:
        subprocess.run(cmd, cwd=REPO_ROOT)
    except KeyboardInterrupt:
        print("\nADK Playground server shut down.")

def run_meals_shortcut(args: list[str] = None) -> None:
    """Main shortcut entry point: parses flags, ensures setup, opens browser, and serves ADK playground."""
    if args is None:
        args = sys.argv[1:]

    if "-h" in args or "--help" in args:
        print("""Usage: meals [OPTIONS]

AI Meal & Grocery Planner Agent (Google ADK Playground).

Options:
  --help, -h       Show this help message and exit.
  --setup          Run the interactive quick setup wizard.
  --cli            Run in terminal CLI mode instead of web playground.
  --no-browser     Do not automatically open the web browser.
  --port=PORT      Port to serve the playground on (default: 8080).
  --host=HOST      Host to bind to (default: 127.0.0.1).
""")
        return

    is_cli = "--cli" in args
    is_setup = "--setup" in args
    no_browser = "--no-browser" in args

    port = 8080
    host = "127.0.0.1"
    data_dir = "data"

    for arg in args:
        if arg.startswith("--port="):
            try:
                port = int(arg.split("=")[1])
            except ValueError:
                pass
        elif arg.startswith("--host="):
            host = arg.split("=")[1]
        elif not arg.startswith("--"):
            data_dir = arg

    data_dir = resolve_data_dir(data_dir)
    profile = load_user_profile(data_dir)
    if profile is None or is_setup:
        profile = quick_setup_wizard(data_dir=data_dir, force=is_setup)

    if is_cli:
        run_interactive_cli(data_dir=data_dir)
        return

    serve_adk_playground(port=port, host=host, data_dir=data_dir, auto_open_browser=(not no_browser))

if __name__ == "__main__":
    run_meals_shortcut()

