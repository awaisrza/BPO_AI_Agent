"""List campaigns and bots from Supabase (find IDs for --campaign-id / --bot-id).

Usage:
  python scripts/list_supabase.py
"""

from __future__ import annotations

import sys

from _env import load_agent_env

load_agent_env()

try:
    from app.supabase_scripts import ScriptLoadError, list_bots, list_campaigns
except ImportError:
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
    from app.supabase_scripts import ScriptLoadError, list_bots, list_campaigns


def main() -> None:
    try:
        campaigns = list_campaigns()
        bots = list_bots()
    except ScriptLoadError as exc:
        print(exc)
        sys.exit(1)

    print("\n--- CAMPAIGNS (use --campaign-id) ---")
    if not campaigns:
        print("  (none)")
    for c in campaigns:
        print(f"  {c['name']}")
        print(f"    id: {c['id']}")

    print("\n--- BOTS (use --bot-id) ---")
    if not bots:
        print("  (none)")
    for b in bots:
        camp = b.get("campaigns") or {}
        camp_name = camp.get("name") if isinstance(camp, dict) else "—"
        print(f"  {b['name']} → campaign: {camp_name}")
        print(f"    id: {b['id']}")

    print("\nExample:")
    if campaigns:
        print(f"  python -m app.main --live --campaign-id {campaigns[0]['id']}")
    if bots:
        print(f"  python -m app.main --live --bot-id {bots[0]['id']}")


if __name__ == "__main__":
    main()
