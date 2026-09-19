"""Command-line entry points for local development and deployment tasks.

    python -m app.cli init      create tables
    python -m app.cli seed      load the synthetic demonstration dataset
    python -m app.cli sweep     run a surveillance sweep now
"""

from __future__ import annotations

import argparse
import json
import sys

from .db import Base, SessionLocal, engine


def cmd_init() -> int:
    Base.metadata.create_all(bind=engine)
    print("Schema created.")
    return 0


def cmd_seed(days: int, seed_value: int) -> int:
    from .seed import seed

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = seed(db, seed_value=seed_value, days=days)
    finally:
        db.close()

    if result.get("status") == "skipped":
        print("Database already contains data; nothing was seeded.", file=sys.stderr)
        return 1

    print(json.dumps({k: v for k, v in result.items() if k != "accounts"}, indent=2))
    print("\nSign in with any of:")
    for account in result.get("accounts", []):
        print(f"  {account['email']:34s} {account['role']}")
    print(f"\nPassword for all demo accounts: {result['password']}")
    return 0


def cmd_sweep(window_days: int) -> int:
    from .services.surveillance import run_sweep

    db = SessionLocal()
    try:
        result = run_sweep(db, window_days=window_days)
    finally:
        db.close()

    print(
        f"Considered {result['reports_considered']} reports; "
        f"detected {result['clusters_detected']} cluster(s)."
    )
    for cluster in result["clusters"]:
        print(f"  - {cluster['cluster_id']}: {cluster['explanation']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vanraksha", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database schema")

    seed_parser = sub.add_parser("seed", help="load the synthetic demonstration dataset")
    seed_parser.add_argument("--days", type=int, default=90)
    seed_parser.add_argument("--seed", type=int, default=2026, dest="seed_value")

    sweep_parser = sub.add_parser("sweep", help="run a surveillance sweep")
    sweep_parser.add_argument("--window-days", type=int, default=21)

    args = parser.parse_args(argv)

    if args.command == "init":
        return cmd_init()
    if args.command == "seed":
        return cmd_seed(args.days, args.seed_value)
    if args.command == "sweep":
        return cmd_sweep(args.window_days)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
