#!/usr/bin/env python3
"""Clear hand-over history for asset C-MU001-0014 and restore previous-owner docs.

Unlike undo_handover_asset_113.py, this does NOT change owner/branch/code or
delete documents. It only:
  1. Deletes rows in asset_ownership_history for the asset
  2. Reclassifies doc_category 'previous_owner' -> 'supporting'
"""

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "production_assets.db"
ASSET_CODE = "C-MU001-0014"


def connect(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def resolve_asset_id(conn):
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, asset_code, owner, branch, department, used_status, name "
        "FROM assets WHERE asset_code = ?",
        (ASSET_CODE,),
    ).fetchall()
    if not rows:
        print(f"ERROR: No asset with code {ASSET_CODE!r}", file=sys.stderr)
        sys.exit(1)
    if len(rows) > 1:
        print(
            f"ERROR: Multiple assets with code {ASSET_CODE!r}: "
            f"{[r['id'] for r in rows]}",
            file=sys.stderr,
        )
        sys.exit(1)
    return int(rows[0]["id"])


def show(conn, asset_id, label):
    cur = conn.cursor()
    print(f"\n=== {label} ===")
    asset = cur.execute(
        "SELECT id, asset_code, owner, branch, department, used_status, name "
        "FROM assets WHERE id = ?",
        (asset_id,),
    ).fetchone()
    print("asset:", dict(asset) if asset else None)

    hist = cur.execute(
        "SELECT id, asset_code, from_branch, to_branch, from_owner, to_owner, "
        "notes, handed_over_at "
        "FROM asset_ownership_history WHERE asset_id = ? ORDER BY id",
        (asset_id,),
    ).fetchall()
    print("history:")
    for row in hist:
        print(" ", dict(row))
    if not hist:
        print("  (none)")

    docs = cur.execute(
        "SELECT id, original_filename, doc_category, created_at "
        "FROM asset_documents WHERE asset_id = ? ORDER BY id",
        (asset_id,),
    ).fetchall()
    print("documents:")
    for row in docs:
        print(" ", dict(row))
    if not docs:
        print("  (none)")


def apply(conn, asset_id):
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM asset_ownership_history WHERE asset_id = ?",
        (asset_id,),
    )
    print(f"deleted history: {cur.rowcount} row(s)")

    cur.execute(
        """
        UPDATE asset_documents
        SET doc_category = 'supporting'
        WHERE asset_id = ?
          AND doc_category = 'previous_owner'
        """,
        (asset_id,),
    )
    print(f"restored supporting docs: {cur.rowcount} row(s)")

    conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description=(
            f"Remove hand-over history for {ASSET_CODE} and reclassify "
            "previous_owner documents as supporting."
        ),
    )
    parser.add_argument(
        "--db",
        default=str(DB_PATH),
        help="Path to production_assets.db",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes (default is dry-run only)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = connect(db_path)
    try:
        asset_id = resolve_asset_id(conn)
        print(f"Resolved {ASSET_CODE} -> asset_id={asset_id}")
        show(conn, asset_id, "BEFORE")
        if not args.apply:
            print("\nDry-run only. Re-run with --apply to write changes.")
            return
        apply(conn, asset_id)
        show(conn, asset_id, "AFTER")
        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
