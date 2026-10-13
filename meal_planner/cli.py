import os
import sys
import time
import threading
import webbrowser
import subprocess
from datetime import datetime
from meal_planner.agent import get_agent_tools, build_system_instruction
from meal_planner.tools.onboarding import resolve_timezone
from meal_planner.tools.memory import MemoryManager
from meal_planner.tools.artifacts import (
    get_current_cycle_prefix,
    get_meal_plan_csv,
    get_grocery_list_csv,
    get_batch_cook_csv,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(REPO_ROOT, ".env")

try:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH, override=True)
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
    from meal_planner.key_manager import save_api_keys
    env_file = getattr(sys.modules[__name__], "ENV_PATH", env_path)
    save_api_keys([api_key], env_path=env_file)

def ensure_api_key(input_fn=None) -> str:
    """Checks for configured Gemini API keys, prompts the user if missing, and optionally persists to .env."""
    if input_fn is None:
        input_fn = input
    from meal_planner.key_manager import get_api_keys, save_api_keys, key_manager

    env_file = getattr(sys.modules[__name__], "ENV_PATH", ENV_PATH)
    keys = get_api_keys(env_file)
    if keys:
        key_manager.set_keys(keys)
        os.environ["GEMINI_API_KEY"] = keys[0]
        os.environ["GOOGLE_API_KEY"] = keys[0]
        return keys[0]

    collected_keys: list[str] = []
    try:
        first = input_fn("Enter Gemini API key: ").strip()
        if not first:
            return ""
        for sub in first.split(","):
            sub_clean = sub.strip()
            if sub_clean and sub_clean not in collected_keys:
                collected_keys.append(sub_clean)

        while True:
            try:
                next_input = input_fn("Enter another Gemini API key (press Enter when done): ").strip()
            except (KeyboardInterrupt, EOFError, StopIteration, IndexError):
                break
            if not next_input:
                break
            if next_input in collected_keys:
                break
            for sub in next_input.split(","):
                sub_clean = sub.strip()
                if sub_clean and sub_clean not in collected_keys:
                    collected_keys.append(sub_clean)
    except (KeyboardInterrupt, EOFError, StopIteration, IndexError):
        if not collected_keys:
            return ""

    if not collected_keys:
        return ""

    save_api_keys(collected_keys, env_path=env_file)
    key_manager.set_keys(collected_keys)
    if len(collected_keys) == 1:
        print("[OK] Saved API key.")
    else:
        print(f"[OK] Saved {len(collected_keys)} API keys.")
    return collected_keys[0]

def quick_setup_wizard(
    data_dir: str = "data",
    input_fn=None,
    force: bool = False
) -> None:
    """Quick setup wizard: prompts for API keys if missing (or when force=True to edit/update)."""
    if input_fn is None:
        input_fn = input
    data_dir = resolve_data_dir(data_dir)

    from meal_planner.key_manager import get_api_keys, save_api_keys, key_manager

    env_file = getattr(sys.modules[__name__], "ENV_PATH", ENV_PATH)
    current_keys = get_api_keys(env_file)
    if not current_keys or force:
        collected_keys: list[str] = []
        try:
            first = input_fn("Enter Gemini API key: ").strip()
            if first:
                for sub in first.split(","):
                    sub_clean = sub.strip()
                    if sub_clean and sub_clean not in collected_keys:
                        collected_keys.append(sub_clean)

                while True:
                    try:
                        next_input = input_fn("Enter another Gemini API key (press Enter when done): ").strip()
                    except (KeyboardInterrupt, EOFError, StopIteration, IndexError):
                        break
                    if not next_input:
                        break
                    if next_input in collected_keys:
                        break
                    for sub in next_input.split(","):
                        sub_clean = sub.strip()
                        if sub_clean and sub_clean not in collected_keys:
                            collected_keys.append(sub_clean)
        except (KeyboardInterrupt, EOFError, StopIteration, IndexError):
            pass

        if collected_keys:
            save_api_keys(collected_keys, env_path=env_file)
            key_manager.set_keys(collected_keys)
            if len(collected_keys) == 1:
                print("[OK] Saved API key.")
            else:
                print(f"[OK] Saved {len(collected_keys)} API keys.")


def run_interactive_cli(data_dir: str = "data") -> None:
    """Runs the interactive Meal Planner agent terminal session."""
    print("=" * 70)
    print("  === AI Meal & Grocery Planner Agent (Gemini ADK) ===")
    print("=" * 70)

    data_dir = resolve_data_dir(data_dir)
    user_tz = "Europe/Brussels"
    try:
        local_tz = datetime.now().astimezone().tzinfo
        if hasattr(local_tz, "key") and local_tz.key:
            user_tz = local_tz.key
    except Exception:
        pass

    tools = get_agent_tools(data_dir)
    tools_map = {t.__name__: t for t in tools}

    # 1. Blank-slate memory hydration
    print("\n[*] Hydrating relevant context files from blank slate...")
    mem_mgr = MemoryManager(data_dir)
    records, total_ms = mem_mgr.hydrate(user_timezone=user_tz)
    for label, path, elapsed_ms in records:
        print(f"  - [Loaded] {label}: {path} ({elapsed_ms:.2f} ms)")
    print(f"[OK] Relevant context hydrated in {total_ms:.2f} ms.")

    sys_instruction = build_system_instruction(user_tz, data_dir=data_dir)

    # 2. Check and prompt for API key if missing
    api_key = ensure_api_key()
    from meal_planner.key_manager import key_manager, is_retryable_api_error
    if key_manager.total_keys() > 0:
        print(f"[*] API Key Pool: {key_manager.total_keys()} key(s) loaded with auto-rotation fallback.")
    if not api_key:
        print("\nRunning in local deterministic mode.")
        print("Type /exit to quit.\n")

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

    print(f"\nTimezone: {user_tz}")
    print("You can chat naturally.")
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
                print(tools_map["tool_get_meal_plan"]())
                continue
            elif user_input == "/groceries":
                print(tools_map["tool_get_grocery_list"]())
                continue
            elif user_input == "/batch":
                print(tools_map["tool_get_batch_cook"]())
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
                total_keys = max(1, key_manager.total_keys())
                max_retries = max(3, total_keys * 2)
                candidate_models = [model_name]
                for fb in ["gemini-3-flash-preview", "gemini-flash-latest"]:
                    if fb not in candidate_models:
                        candidate_models.append(fb)
                model_idx = 0
                attempts = 0
                current_model = candidate_models[0]
                while attempts < max_retries:
                    try:
                        response = chat.send_message(user_input)
                        print(f"\nAgent > {response.text}\n")
                        handled_by_gemini = True
                        break
                    except Exception as e:
                        if not is_retryable_api_error(e) or attempts >= max_retries - 1:
                            print(f"\n[!] Gemini API error ({e}). Falling back to local execution.\n")
                            break
                        attempts += 1
                        err_str = str(e).upper()
                        if ("503" in err_str or "UNAVAILABLE" in err_str or attempts % total_keys == 0) and len(candidate_models) > 1:
                            model_idx += 1
                            current_model = candidate_models[model_idx % len(candidate_models)]
                        next_key = key_manager.rotate_key()
                        delay = min(2.0, 0.4 * attempts)
                        print(f"\n[KeyManager] Rate limit / API error ({e}). Rotating to API key {key_manager.current_index + 1}/{total_keys} (model: {current_model}) and retrying in {delay:.1f}s (attempt {attempts + 1}/{max_retries})...\n")
                        if delay > 0:
                            time.sleep(delay)
                        try:
                            client = genai.Client(api_key=next_key)
                            chat_history = chat.get_history()
                            config = types.GenerateContentConfig(
                                system_instruction=sys_instruction,
                                tools=tools,
                                temperature=0.2
                            )
                            chat = client.chats.create(model=current_model, config=config, history=chat_history)
                        except Exception as rebuild_err:
                            print(f"[KeyManager] Could not rebuild chat with new key: {rebuild_err}")

            if not handled_by_gemini:
                # Local fallback parser for key actions
                lower = user_input.lower()
                if "schedule" in lower or "what is my schedule" in lower or ("meal" in lower and "plan" in lower):
                    prefix = get_current_cycle_prefix(user_tz)
                    active_plan = os.path.join(data_dir, "plans", f"{prefix}_meal_plan.csv")
                    print(f"\nAgent > Your weekly meal plan is stored at: {active_plan}\n(Ask me explicitly to 'print the plan' if you wish to see all rows in chat).\n")
                elif "print the plan" in lower or "show the plan" in lower:
                    rows = get_meal_plan_csv(data_dir)
                    if rows:
                        lines = ["| Date | Meal | Recipe | Ingredients | P | C | F | Kcal |", "|---|---|---|---|---|---|---|---|"]
                        for r in rows:
                            lines.append(f"| {r.get('Date')} | {r.get('Meal')} | {r.get('Recipe')} | {r.get('Ingredient')} | {r.get('P')} | {r.get('C')} | {r.get('F')} | {r.get('Calories')} |")
                        print(f"\nAgent >\n" + "\n".join(lines) + "\n")
                    else:
                        print("\nAgent > No meal plan found.\n")
                elif "groceries" in lower or "grocery" in lower:
                    rows = get_grocery_list_csv(data_dir)
                    if rows:
                        lines = ["| Run | Category | Item | Quantity_g | Estimated_Price_EUR |", "|---|---|---|---|---|"]
                        for r in rows:
                            lines.append(f"| {r.get('Run')} | {r.get('Category')} | {r.get('Item')} | {r.get('Quantity_g')} | {r.get('Estimated_Price_EUR')} |")
                        print(f"\nAgent >\n" + "\n".join(lines) + "\n")
                    else:
                        print("\nAgent > No grocery list found.\n")
                elif "batch" in lower:
                    rows = get_batch_cook_csv(data_dir)
                    if rows:
                        lines = ["| Dish | Main Protein | Meals |", "|---|---|---|"]
                        for r in rows:
                            lines.append(f"| {r.get('Dish')} | {r.get('Main_Protein')} | {r.get('Meals')} |")
                        print(f"\nAgent >\n" + "\n".join(lines) + "\n")
                    else:
                        print("\nAgent > No batch cook instructions found.\n")
                else:
                    print("\nAgent > Command received. Set GEMINI_API_KEY to enable full live LLM reasoning for any natural language input.\n")

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

    # 1. API key verification (only if missing)
    from meal_planner.key_manager import get_api_keys, key_manager
    env_file = getattr(sys.modules[__name__], "ENV_PATH", ENV_PATH)
    keys = get_api_keys(env_file)
    if not keys:
        ensure_api_key()
        keys = get_api_keys(env_file)
    key_manager.set_keys(keys)
    if keys:
        os.environ["GEMINI_API_KEYS"] = ",".join(keys)
        os.environ["GEMINI_API_KEY"] = keys[0]
        os.environ["GOOGLE_API_KEY"] = keys[0]
        print(f"[*] API Key Pool: {len(keys)} key(s) loaded with auto-rotation fallback.")

    user_tz = "Europe/Brussels"
    try:
        local_tz = datetime.now().astimezone().tzinfo
        if hasattr(local_tz, "key") and local_tz.key:
            user_tz = local_tz.key
    except Exception:
        pass

    # 2. Blank-slate memory hydration (only relevant files)
    print("\n[*] Hydrating relevant context files from blank slate...")
    mem_mgr = MemoryManager(data_dir)
    records, total_ms = mem_mgr.hydrate(user_timezone=user_tz)
    for label, path, elapsed_ms in records:
        print(f"  - [Loaded] {label}: {path} ({elapsed_ms:.2f} ms)")
    print(f"[OK] Relevant context hydrated in {total_ms:.2f} ms.")

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
        subprocess.run(cmd, cwd=REPO_ROOT, env=dict(os.environ))
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
    from meal_planner.key_manager import get_api_keys
    env_file = getattr(sys.modules[__name__], "ENV_PATH", ENV_PATH)
    keys = get_api_keys(env_file)
    if is_setup or not keys:
        quick_setup_wizard(data_dir=data_dir, force=is_setup)
        if is_setup:
            print("\n[OK] Setup complete. Run 'meals' to launch the agent playground.")
            return

    if is_cli:
        run_interactive_cli(data_dir=data_dir)
        return

    serve_adk_playground(port=port, host=host, data_dir=data_dir, auto_open_browser=(not no_browser))

if __name__ == "__main__":
    run_meals_shortcut()

