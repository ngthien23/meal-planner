AI Meal & Grocery Planner Agent: Requirements Specification

1. Core Objective
To act as a dynamic, highly personalized dietary and financial planner that generates macro-accurate meal schedules and zero-waste grocery lists. The agent must prioritize the user's specific lifestyle constraints, including powerlifting nutritional targets, budget optimization, and texture-based eating habits (e.g., chewing fatigue).

2. Module 1: Preference & Profile Management (Understanding Preferences)
The agent must store, recall, and actively apply a complex set of user preferences:

Texture & Fatigue Rules: Must schedule soft, liquid, or broth-based meals (e.g., Phở, thinly sliced meat in hot broth) for breakfasts and dinners. Solid, batch-cooked savory meals are strictly for lunch.

Ingredient Restrictions: No dairy milk (fortified soy only due to acne), no non-Optimum Nutrition whey (digestive issues), no fresh tuna (canned only).

Flavor Profile: Heavy emphasis on Vietnamese cuisine (Thịt kho, Gà xào sả ớt) and savory profiles.

Lifestyle Constraints: Batch cooking is limited to Sunday and Wednesday evenings. Workday lunches must be reheatable.

Timezone & Temporal Anchoring: Must prompt for and store the user's timezone during initial onboarding. Must maintain temporal awareness using the user's local timezone to interpret relative references (e.g., "today", "tonight", "tomorrow's lunch", "Thursday night").

3. Module 2: Macro & Caloric Calculation Engine
The agent must dynamically calculate daily and weekly nutritional targets based on variable inputs rather than static numbers:

Dynamic Inputs: Current bodyweight (e.g., 65 kg), goal state (e.g., lean bulk), and user-defined multipliers (e.g., 2.3g Protein/kg, 1g+ Fat/kg, remaining calories to Carbohydrates).

Flat Macro Adherence: Once targets are set (e.g., 155g P / 70g F / 330g C), the agent must build daily meal plans that keep carbohydrate and fat sources relatively flat across the week, swapping only the raw weights of protein sources (chicken, beef, pork, shrimp) to hit the daily goal.

4. Module 3: Plan Generation Engine (Meals & Groceries)
The agent must generate actionable, highly structured outputs:

Raw Weight Precision: All meal plans must dictate raw/dry ingredient weights (e.g., "110g dry rice noodles", "200g raw lean beef") to ensure accurate macro tracking.

Zero-Waste Algorithm: The agent must exhaust standard package sizes (e.g., splitting exactly a 1kg bag of frozen shrimp across four dinners) so no perishable food goes to waste.

Split Grocery Logistics: Grocery lists must automatically divide into a "Saturday Run" and a "Wednesday Run" to ensure fresh meat is never stored in the fridge longer than 48-72 hours.

5. Module 4: Database, Tracking, & Analytics
The agent must function as a database manager capable of reading, writing, and analyzing structured data (Text/CSV):

Price Tracking: Log and monitor the unit prices of frequent purchases (e.g., Optimum Nutrition Whey price per kg, Colruyt Boni frozen avocado chunks, chicken breast).

Artifact Generation: Output weekly CSVs of grocery costs, daily macros, and meal logs.

Trend Reporting: Generate summaries upon request (e.g., "Show me my average weekly spend on protein sources over the last month," or "Graph my caloric adherence vs. grocery spend").

6. Module 5: Dynamic Adaptation (Real-Time Inputs)
The agent must be able to pivot the schedule based on real-world friction and user feedback:

Meal Deviations: If the user inputs, "I was too tired to cook Thursday night and drank a double shake instead," the agent must instantly adjust Friday's macros and roll over the unused beef/shrimp to the weekend to prevent spoilage.

Grocery Adjustments: If a targeted ingredient is out of stock or overpriced (e.g., "Pork shoulder was €15/kg today so I bought extra chicken"), the agent must recalculate the upcoming lunches and update the financial tracker.

Preference Shifts: Seamlessly integrate new baseline rules (e.g., "I'm cutting to 63kg now, drop the carbs to 250g") and instantly regenerate the current week's remaining meals and the next grocery list.