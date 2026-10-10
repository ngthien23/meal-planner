import os
import json
from datetime import datetime
from typing import Optional

from meal_planner.models import (
    InventoryItem,
    InventoryState,
    load_catalog,
)

__all__ = [
    "InventoryItem",
    "InventoryState",
    "load_inventory_state",
    "save_inventory_state",
    "record_actual_stock",
]


def load_inventory_state(data_dir: str) -> InventoryState:
    """Loads inventory state from inventory.json in data_dir.
    
    If the file does not exist, returns an empty default InventoryState.
    """
    inventory_path = os.path.join(data_dir, "inventory.json")
    if not os.path.exists(inventory_path):
        return InventoryState(
            last_reconciled_at=None,
            carried_calories=0.0,
            carried_protein_g=0.0,
            items=[]
        )

    try:
        with open(inventory_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return InventoryState(
                last_reconciled_at=None,
                carried_calories=0.0,
                carried_protein_g=0.0,
                items=[]
            )

        items = [
            InventoryItem(
                food_id=item["food_id"],
                name=item.get("name", item["food_id"].replace("_", " ").title()),
                quantity_g=float(item.get("quantity_g", 0.0)),
                status=item.get("status", "actual"),
                source=item.get("source", "user_report"),
                purchased_date=item.get("purchased_date", "")
            )
            for item in data.get("items", [])
        ]

        return InventoryState(
            last_reconciled_at=data.get("last_reconciled_at"),
            carried_calories=float(data.get("carried_calories", 0.0)),
            carried_protein_g=float(data.get("carried_protein_g", 0.0)),
            items=items
        )
    except Exception:
        return InventoryState(
            last_reconciled_at=None,
            carried_calories=0.0,
            carried_protein_g=0.0,
            items=[]
        )


def save_inventory_state(data_dir: str, state: InventoryState) -> None:
    """Persists inventory state to inventory.json in data_dir."""
    os.makedirs(data_dir, exist_ok=True)
    inventory_path = os.path.join(data_dir, "inventory.json")

    data = {
        "last_reconciled_at": state.last_reconciled_at,
        "carried_calories": round(float(state.carried_calories), 2),
        "carried_protein_g": round(float(state.carried_protein_g), 2),
        "items": [
            {
                "food_id": item.food_id,
                "name": item.name,
                "quantity_g": round(float(item.quantity_g), 2),
                "status": item.status,
                "source": item.source,
                "purchased_date": item.purchased_date
            }
            for item in state.items
        ]
    }

    with open(inventory_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def record_actual_stock(
    data_dir: str,
    items: list[dict],
    clear_unbought_run_meats: bool = True
) -> InventoryState:
    """Updates inventory state with user-reported actual stock items.
    
    If clear_unbought_run_meats is True, assumed perishable meats from upcoming
    planned runs are pruned so duplicate meat is not bought.
    Matching food_ids are updated with status='actual' and source='user_report',
    and new food_ids are appended.
    """
    state = load_inventory_state(data_dir)

    if clear_unbought_run_meats:
        try:
            catalog_ingredients, _ = load_catalog(data_dir=data_dir)
        except Exception:
            catalog_ingredients = {}

        def is_meat_or_perishable(food_id: str) -> bool:
            if food_id in catalog_ingredients:
                ing = catalog_ingredients[food_id]
                return bool(ing.perishable and (ing.category in ("meat", "seafood", "poultry") or "meat" in ing.category.lower()))
            lower_id = food_id.lower()
            if "canned" in lower_id or "dried" in lower_id:
                return False
            keywords = ("chicken", "beef", "pork", "meat", "shrimp", "fish", "salmon", "turkey", "lamb", "steak", "thigh", "wing", "breast")
            return any(k in lower_id for k in keywords)

        state.items = [
            item for item in state.items
            if not (item.status == "assumed" and is_meat_or_perishable(item.food_id))
        ]

    today_str = datetime.now().strftime("%Y-%m-%d")

    for raw_item in items:
        food_id = raw_item["food_id"]
        name = raw_item.get("name") or food_id.replace("_", " ").title()
        quantity_g = float(raw_item.get("quantity_g", 0.0))
        purchased_date = raw_item.get("purchased_date") or today_str
        source = raw_item.get("source", "user_report")
        status = "actual"

        existing = next((i for i in state.items if i.food_id == food_id), None)
        if existing:
            existing.name = name
            existing.quantity_g = quantity_g
            existing.status = status
            existing.source = source
            existing.purchased_date = purchased_date
        else:
            state.items.append(
                InventoryItem(
                    food_id=food_id,
                    name=name,
                    quantity_g=quantity_g,
                    status=status,
                    source=source,
                    purchased_date=purchased_date
                )
            )

    save_inventory_state(data_dir, state)
    return state
