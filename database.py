
import sqlite3
import hashlib
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "tracker.db")

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode          TEXT,
            status           TEXT DEFAULT 'WIP',
            original_filename TEXT,
            vendor_name      TEXT,
            doc_number       TEXT,
            dices_reference  TEXT,
            po_number        TEXT,
            doc_amount       REAL,
            regions          TEXT,
            doc_type         TEXT,
            action_required  TEXT,
            action_taken     TEXT,
            category         TEXT,
            auditor          TEXT,
            comments         TEXT,
            date_ingested    TEXT,
            date_actioned    TEXT,
            days_to_action   INTEGER,
            last_updated     TEXT,
            updated_by       TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            field_changed  TEXT,
            old_value      TEXT,
            new_value      TEXT,
            changed_by     TEXT,
            changed_at     TEXT
        )
    """)

    # Default admin password: admin123
    c.execute("INSERT OR IGNORE INTO settings VALUES ('admin_password', ?)",
              (hash_password("admin123"),))

    # Default categories
    default_cats = [
        "Invoice - Regular", "Invoice - Utility", "Credit Memo",
        "Duplicate", "Missing PO", "Price Discrepancy",
        "Receiving Issue", "Other"
    ]
    for cat in default_cats:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))

    conn.commit()
    conn.close()

def verify_admin(password):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key='admin_password'")
    row = c.fetchone()
    conn.close()
    if row:
        return row["value"] == hash_password(password)
    return False

def change_admin_password(new_password):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE settings SET value=? WHERE key='admin_password'",
              (hash_password(new_password),))
    conn.commit()
    conn.close()

def get_categories():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name FROM categories ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return [r["name"] for r in rows]

def add_category(name):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (name,))
    conn.commit()
    conn.close()

def delete_category(name):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM categories WHERE name=?", (name,))
    conn.commit()
    conn.close()

def get_all_transactions(filters=None):
    conn = get_conn()
    c = conn.cursor()
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if filters:
        if filters.get("status"):
            query += " AND status=?"
            params.append(filters["status"])
        if filters.get("auditor"):
            query += " AND auditor=?"
            params.append(filters["auditor"])
        if filters.get("region"):
            query += " AND regions=?"
            params.append(filters["region"])
        if filters.get("category"):
            query += " AND category=?"
            params.append(filters["category"])
        if filters.get("search"):
            s = "%" + filters["search"] + "%"
            query += " AND (barcode LIKE ? OR vendor_name LIKE ? OR doc_number LIKE ? OR po_number LIKE ?)"
            params.extend([s, s, s, s])
    query += " ORDER BY id DESC"
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_transaction_by_id(txn_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE id=?", (txn_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def update_transaction(txn_id, updates, updated_by):
    conn = get_conn()
    c = conn.cursor()

    # Get old values for audit log
    c.execute("SELECT * FROM transactions WHERE id=?", (txn_id,))
    old = dict(c.fetchone())

    # Auto date_actioned
    actionable_statuses = ["Completed", "Rejected", "Closed", "Voided"]
    now = datetime.now().strftime("%Y-%m-%d")
    now_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if "status" in updates and updates["status"] in actionable_statuses:
        if not old.get("date_actioned"):
            updates["date_actioned"] = now

    # Calculate days_to_action
    if "date_actioned" in updates and updates["date_actioned"]:
        di = old.get("date_ingested")
        if di:
            try:
                d1 = datetime.strptime(di[:10], "%Y-%m-%d")
                d2 = datetime.strptime(updates["date_actioned"][:10], "%Y-%m-%d")
                updates["days_to_action"] = (d2 - d1).days
            except:
                pass

    updates["last_updated"] = now_full
    updates["updated_by"] = updated_by

    set_clause = ", ".join([f"{k}=?" for k in updates.keys()])
    values = list(updates.values()) + [txn_id]
    c.execute(f"UPDATE transactions SET {set_clause} WHERE id=?", values)

    # Audit log
    for field, new_val in updates.items():
        if field not in ("last_updated", "updated_by"):
            old_val = old.get(field)
            if str(old_val) != str(new_val):
                c.execute("""
                    INSERT INTO audit_log
                    (transaction_id, field_changed, old_value, new_value, changed_by, changed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (txn_id, field, old_val, new_val, updated_by, now_full))

    conn.commit()
    conn.close()

def ingest_excel(df, mode="add_new"):
    """
    mode='add_new'    : only insert rows not already in DB (by barcode)
    mode='full_replace': clear all + re-insert (keeps user edits for existing barcodes)
    """
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d")
    added = 0
    skipped = 0

    # Map df columns to db columns
    col_map = {
        "Barcode":               "barcode",
        "Status":                "status",
        "Original Filename":     "original_filename",
        "Vendor/Supplier Name":  "vendor_name",
        "Vendor / Supplier Name":"vendor_name",
        "Doc Number":            "doc_number",
        "DICES Reference":       "dices_reference",
        "PO Number":             "po_number",
        "Doc Amount":            "doc_amount",
        "Regions":               "regions",
        "Doc Type":              "doc_type",
        "Action Required":       "action_required",
        "Action Taken":          "action_taken",
        "Category":              "category",
        "Auditor":               "auditor",
        "Comments":              "comments",
    }

    for _, row in df.iterrows():
        barcode = str(row.get("Barcode", "")).strip()
        if not barcode:
            continue

        if mode == "add_new":
            c.execute("SELECT id FROM transactions WHERE barcode=?", (barcode,))
            existing = c.fetchone()
            if existing:
                skipped += 1
                continue

        rec = {"date_ingested": now, "status": "WIP"}
        for excel_col, db_col in col_map.items():
            if excel_col in df.columns:
                val = row.get(excel_col)
                if val is not None and str(val).strip() not in ("", "nan", "NaN"):
                    rec[db_col] = str(val).strip() if db_col != "doc_amount" else float(val) if val else None

        cols = ", ".join(rec.keys())
        placeholders = ", ".join(["?"] * len(rec))
        c.execute(f"INSERT INTO transactions ({cols}) VALUES ({placeholders})",
                  list(rec.values()))
        added += 1

    conn.commit()
    conn.close()
    return added, skipped

def get_dashboard_stats():
    conn = get_conn()
    c = conn.cursor()

    stats = {}

    # Status counts
    c.execute("SELECT status, COUNT(*) as cnt FROM transactions GROUP BY status")
    stats["status_counts"] = {r["status"]: r["cnt"] for r in c.fetchall()}

    # Aging
    c.execute("""
        SELECT
            SUM(CASE WHEN days_to_action BETWEEN 0 AND 7  THEN 1 ELSE 0 END) as d0_7,
            SUM(CASE WHEN days_to_action BETWEEN 8 AND 14 THEN 1 ELSE 0 END) as d8_14,
            SUM(CASE WHEN days_to_action BETWEEN 15 AND 30 THEN 1 ELSE 0 END) as d15_30,
            SUM(CASE WHEN days_to_action > 30              THEN 1 ELSE 0 END) as d30plus
        FROM transactions
        WHERE status NOT IN ('Completed','Closed','Voided')
          AND days_to_action IS NOT NULL
    """)
    row = c.fetchone()
    stats["aging"] = dict(row) if row else {}

    # KPIs
    c.execute("SELECT COUNT(*) as total FROM transactions")
    stats["total"] = c.fetchone()["total"]

    c.execute("SELECT AVG(days_to_action) as avg FROM transactions WHERE days_to_action IS NOT NULL")
    avg = c.fetchone()["avg"]
    stats["avg_days"] = round(avg, 1) if avg else 0

    c.execute("SELECT COUNT(*) as cnt FROM transactions WHERE status IN ('WIP','Pending Supplier')")
    stats["open"] = c.fetchone()["cnt"]

    c.execute("SELECT COUNT(*) as cnt FROM transactions WHERE status='Completed'")
    stats["completed"] = c.fetchone()["cnt"]

    # By Category
    c.execute("SELECT category, COUNT(*) as cnt FROM transactions WHERE category IS NOT NULL AND category != '' GROUP BY category ORDER BY cnt DESC LIMIT 8")
    stats["by_category"] = [(r["category"], r["cnt"]) for r in c.fetchall()]

    # By Auditor
    c.execute("SELECT auditor, COUNT(*) as cnt FROM transactions WHERE auditor IS NOT NULL AND auditor != '' GROUP BY auditor ORDER BY cnt DESC LIMIT 10")
    stats["by_auditor"] = [(r["auditor"], r["cnt"]) for r in c.fetchall()]

    conn.close()
    return stats

def get_audit_log(txn_id=None, limit=100):
    conn = get_conn()
    c = conn.cursor()
    if txn_id:
        c.execute("SELECT * FROM audit_log WHERE transaction_id=? ORDER BY changed_at DESC LIMIT ?", (txn_id, limit))
    else:
        c.execute("SELECT * FROM audit_log ORDER BY changed_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_all_transactions():
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()

def get_distinct_auditors():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT auditor FROM transactions WHERE auditor IS NOT NULL AND auditor != '' ORDER BY auditor")
    rows = c.fetchall()
    conn.close()
    return [r["auditor"] for r in rows]

def get_distinct_regions():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT regions FROM transactions WHERE regions IS NOT NULL AND regions != '' ORDER BY regions")
    rows = c.fetchall()
    conn.close()
    return [r["regions"] for r in rows]
