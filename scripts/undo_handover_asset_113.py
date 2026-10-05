#!/usr/bin/env python3
"""Undo mistaken Cartoon -> Mishmisha hand-over for asset_id 113."""

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "production_assets.db"
ASSET_ID = 113

# Same doc ids as on the DB you already fixed locally (from server copy)
RESTORE_SUPPORTING_IDS = (173, 174)
DELETE_DOC_IDS = (245, 177)  # hand-over upload + return
RESTORE_CODE = "C-MU001-0004"
RESTORE_OWNER = "No Owner"
RESTORE_BRANCH = "Cartoon"
RESTORE_DEPARTMENT = "Cashier"


def connect(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def show(conn, label):
    cur = conn.cursor()
    print(f"\n=== {label} ===")
    asset = cur.execute(
        "SELECT id, asset_code, owner, branch, department, used_status "
        "FROM assets WHERE id = ?",
        (ASSET_ID,),
    ).fetchone()
    print("asset:", dict(asset) if asset else None)

    hist = cur.execute(
        "SELECT id, asset_code, from_branch, to_branch, notes, handed_over_at "
        "FROM asset_ownership_history WHERE asset_id = ? ORDER BY id",
        (ASSET_ID,),
    ).fetchall()
    print("history:")
    for row in hist:
        print(" ", dict(row))
    if not hist:
        print("  (none)")

    docs = cur.execute(
        "SELECT id, original_filename, doc_category, created_at "
        "FROM asset_documents WHERE asset_id = ? ORDER BY id",
        (ASSET_ID,),
    ).fetchall()
    print("documents:")
    for row in docs:
        print(" ", dict(row))
    if not docs:
        print("  (none)")


def apply(conn):
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE assets
        SET owner = ?, branch = ?, department = ?, asset_code = ?
        WHERE id = ?
        """,
        (RESTORE_OWNER, RESTORE_BRANCH, RESTORE_DEPARTMENT, RESTORE_CODE, ASSET_ID),
    )
    print(f"updated assets: {cur.rowcount} row(s)")

    cur.execute(
        "DELETE FROM asset_ownership_history WHERE asset_id = ?",
        (ASSET_ID,),
    )
    print(f"deleted history: {cur.rowcount} row(s)")

    cur.execute(
        f"""
        UPDATE asset_documents
        SET doc_category = 'supporting'
        WHERE asset_id = ?
          AND id IN ({",".join("?" * len(RESTORE_SUPPORTING_IDS))})
        """,
        (ASSET_ID, *RESTORE_SUPPORTING_IDS),
    )
    print(f"restored supporting docs: {cur.rowcount} row(s)")

    cur.execute(
        f"""
        DELETE FROM asset_documents
        WHERE asset_id = ?
          AND id IN ({",".join("?" * len(DELETE_DOC_IDS))})
        """,
        (ASSET_ID, *DELETE_DOC_IDS),
    )
    print(f"deleted extra docs: {cur.rowcount} row(s)")

    conn.commit()


def main():
    parser = argparse.ArgumentParser()
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
        show(conn, "BEFORE")
        if not args.apply:
            print("\nDry-run only. Re-run with --apply to write changes.")
            return
        apply(conn)
        show(conn, "AFTER")
        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
