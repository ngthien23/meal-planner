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

def save_env_api_key(api_key: str, env_path: str = ENV_PATH) -> None:
    """Saves or updates GEMINI_API_KEY and GOOGLE_API_KEY in the .env file and process environment."""
    os.environ["GEMINI_API_KEY"] = api_key
    os.environ["GOOGLE_API_KEY"] = api_key
    env_file = getattr(sys.modules[__name__], "ENV_PATH", env_path)
    lines = []
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_lines = []
    found_gemini = False
    found_google = False
    for line in lines:
        if line.startswith("GEMINI_API_KEY="):
            new_lines.append(f"GEMINI_API_KEY={api_key}\n")
            found_gemini = True
        elif line.startswith("GOOGLE_API_KEY="):
            new_lines.append(f"GOOGLE_API_KEY={api_key}\n")
            found_google = True
        else:
            new_lines.append(line)

    if not found_gemini:
        new_lines.append(f"GEMINI_API_KEY={api_key}\n")
    if not found_google:
        new_lines.append(f"GOOGLE_API_KEY={api_key}\n")

    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

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
            save_env_api_key(entered)
            print("[OK] GEMINI_API_KEY and GOOGLE_API_KEY saved to .env file.")
    except (KeyboardInterrupt, EOFError):
        pass

    return entered

def quick_setup_wizard(
    data_dir: str = "data",
    input_fn=None,
    force: bool = False
) -> UserProfile:
    """Quick setup wizard: prompts for API key if missing (or when force=True to edit/update)."""
    if input_fn is None:
        input_fn = input
    data_dir = resolve_data_dir(data_dir)
    profile = load_user_profile(data_dir)
    if profile is not None and not force:
        return profile

    current_key = os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()
    if not current_key or force:
        if current_key and force:
            masked = current_key[:4] + "..." + current_key[-4:] if len(current_key) > 8 else "***"
            prompt_str = f"Enter Gemini API key (press Enter to keep current [{masked}]): "
        else:
            prompt_str = "Enter Gemini API key: "

        try:
            entered_key = input_fn(prompt_str).strip()
            if entered_key:
                save_env_api_key(entered_key)
                if not entered_key.startswith("AIzaSy"):
                    print("[!] Note: Standard permanent Gemini API keys start with 'AIzaSy' (from https://aistudio.google.com/app/apikey).")
                    print("    If this is a temporary session token, it may expire after a short time.")
                print("[OK] Saved API key.")
            elif not current_key:
                print("No API key entered. You can set it later by running: meals --setup")
        except (KeyboardInterrupt, EOFError):
            pass

    # Auto-detect default system timezone
    default_tz = "UTC"
    try:
        local_tz = datetime.now().astimezone().tzinfo
        if hasattr(local_tz, "key") and local_tz.key:
            default_tz = local_tz.key
    except Exception:
        pass

    if profile is None:
        profile_data = {
            "timezone": default_tz,
            "bodyweight_kg": 0.0,
            "goal_state": "",
            "target_calories": 0.0,
            "protein_multiplier": 2.0,
            "fat_multiplier": 1.0,
            "restrictions": [],
            "week_start_day": "Monday",
            "weeks_ahead": 1,
            "currency": "EUR",
            "is_onboarded": False,
            "texture_rules": {}
        }
        profile = init_user_profile(data_dir, profile_data)
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

    if profile and profile.is_onboarded and profile.target_calories > 0:
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

    if profile and profile.is_onboarded and profile.target_calories > 0:
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
        if is_setup:
            print("\n[OK] Setup complete. Run 'meals' to launch the agent playground.")
            return

    if is_cli:
        run_interactive_cli(data_dir=data_dir)
        return

    serve_adk_playground(port=port, host=host, data_dir=data_dir, auto_open_browser=(not no_browser))

if __name__ == "__main__":
    run_meals_shortcut()

