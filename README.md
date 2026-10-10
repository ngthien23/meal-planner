# Meal Planner Agent

An AI assistant that plans weekly meals and groceries based on your protein needs, budget, and food preferences. Built with Google ADK (Agent Development Kit) and Gemini.

---

## Requirements

- Python 3.10+
- A Gemini API key (set in `.env` as `GEMINI_API_KEY`)

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/ngthien23/meal-planner.git
   cd meal-planner
   ```

2. Install dependencies:
   ```bash
   pip install -e .
   ```
   *(Or using uv: `uv pip install -e .`)*

3. Set up your Gemini API key:
   ```bash
   meals --setup
   ```
   Alternatively, create a `.env` file in the project root:
   ```env
   GEMINI_API_KEY=your_api_key_here
   ```

---

## Usage

Start the agent and open the web interface in your default browser:
```bash
meals
```

On Windows, you can also run `.\meals` (PowerShell) or `meals.bat`. On macOS/Linux, run `./meals`.

### Options
- `meals` : Starts the Google ADK playground and opens it in your default browser.
- `meals --setup` : Prompts to add or update your Gemini API key.
- `meals --cli` : Runs the agent in interactive terminal mode.
- `meals --no-browser` : Starts the web server without opening a browser window.
- `meals --port=8080` : Runs the web server on a custom port.

---

## How It Works

- **Conversational Onboarding:** Share your stats (bodyweight, target calories, weekly protein budget) and food preferences directly in chat. The agent saves durable preferences in `data/memory/long_term.md`.
- **Short-Term Memory & Stock:** Report on-hand protein or meal deviations in chat; the agent tracks them in `data/memory/weekly.md`.
- **Artifacts:** Plans are written to human-readable CSV files in `data/plans/`:
  - `meal_plan.csv` : Daily recipes and rough macronutrient targets.
  - `batch_cook.csv` : Batch dishes, primary protein amounts, and meal counts.
  - `grocery_list.csv` : Split grocery runs sorted by run and category.
- **Grocery Updates:** The agent reasons about changes (e.g. after shifting runs or using on-hand stock) and asks for your confirmation before updating the grocery list.

---

## Testing

Run the test suite:
```bash
python -m unittest discover -s tests -p "test_*.py"
```
