import os
import sys
from datetime import datetime
from meal_planner.agent import get_agent_tools, build_system_instruction
from meal_planner.tools.onboarding import load_user_profile, init_user_profile, resolve_timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def get_model_name() -> str:
    """Returns the Gemini model to use, defaulting to gemini-3.8-flash."""
    return os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

def run_interactive_cli(data_dir: str = "data") -> None:
    """Runs the interactive Meal Planner agent terminal session."""
    print("=" * 70)
    print("  🏋️  AI Meal & Grocery Planner Agent (Gemini ADK)  🏋️")
    print("=" * 70)

    # 1. Check or perform onboarding
    profile = load_user_profile(data_dir)
    tools = get_agent_tools(data_dir)
    tools_map = {t.__name__: t for t in tools}

    if not profile:
        print("\n👋 Welcome! No athlete profile found. Let's do a quick onboarding setup.")
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

            print("\n⚙️  Initializing your profile and local bookkeeping files...")
            init_msg = tools_map["tool_onboard_user"](tz_name, bw, goal, target_kcal, p_mult, f_mult)
            print(f"✅ {init_msg}")

            print("\n📋 Generating your initial weekly meal plan and split grocery list...")
            plan_msg = tools_map["tool_generate_meal_plan"]()
            print(f"✅ {plan_msg}")

            profile = load_user_profile(data_dir)
        except (KeyboardInterrupt, EOFError):
            print("\nOnboarding aborted.")
            return

    user_tz = profile.timezone if profile else "Europe/Brussels"
    sys_instruction = build_system_instruction(user_tz)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("\n⚠️  Notice: GEMINI_API_KEY environment variable is not set.")
        print("To enable full Gemini agent conversation, set GEMINI_API_KEY=<your-key> in your environment or in a .env file.")
        print("Running in local deterministic mode. Supported commands:")
        print("  /plan        - Re-generate and export meal plan & grocery CSVs")
        print("  /groceries   - View current split grocery list")
        print("  /analytics   - View protein spend & adherence analytics")
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
            print(f"🤖 Gemini Agent ({model_name}) is active and ready!")
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

            # Send to Gemini Chat session if active
            handled_by_gemini = False
            if chat:
                try:
                    response = chat.send_message(user_input)
                    print(f"\nAgent > {response.text}\n")
                    handled_by_gemini = True
                except Exception as e:
                    print(f"\n⚠️  Gemini API error ({e}). Falling back to local execution.\n")

            if not handled_by_gemini:
                # Local fallback parser for key actions
                lower = user_input.lower()
                if "shake" in lower or "missed" in lower or "skip" in lower:
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

if __name__ == "__main__":
    run_interactive_cli()
