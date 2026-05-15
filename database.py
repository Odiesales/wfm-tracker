
import sqlite3
import hashlib
import os
from datetime import datetime, date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "tracker.db")

# ── SLA CONSTANTS ─────────────────────────────────────────
SLA_ACTION_DAYS    = 3   # working days to take action
SLA_COMPLETE_DAYS  = 5   # working days to complete/close

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def add_working_days(start_date, days):
    """Add N working days (Mon-Fri) to a date."""
    current = start_date
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon=0 ... Fri=4
            added += 1
    return current

def working_days_between(start_date, end_date):
    """Count working days between two dates."""
    count = 0
    current = start_date
    while current < end_date:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return count

def get_sla_status(date_ingested_str, status, date_actioned_str=None):
    """
    Returns dict with SLA info:
    - action_sla:   'OK', 'DUE TODAY', 'OVERDUE', 'DONE'
    - complete_sla: 'OK', 'DUE TODAY', 'OVERDUE', 'DONE'
    - action_due_date
    - complete_due_date
    - working_days_open
    """
    if not date_ingested_str:
        return {}
    try:
        ingested = datetime.strptime(date_ingested_str[:10], "%Y-%m-%d").date()
    except:
        return {}

    today = date.today()
    action_due    = add_working_days(ingested, SLA_ACTION_DAYS)
    complete_due  = add_working_days(ingested, SLA_COMPLETE_DAYS)
    working_open  = working_days_between(ingested, today)

    closed_statuses = ["Completed", "Closed", "Rejected", "Voided"]
    is_closed = status in closed_statuses

    # Action SLA
    if date_actioned_str:
        action_sla = "DONE"
    elif is_closed:
        action_sla = "DONE"
    elif today > action_due:
        action_sla = "OVERDUE"
    elif today == action_due:
        action_sla = "DUE TODAY"
    else:
        action_sla = "OK"

    # Complete SLA
    if is_closed:
        complete_sla = "DONE"
    elif today > complete_due:
        complete_sla = "OVERDUE"
    elif today == complete_due:
        complete_sla = "DUE TODAY"
    else:
        complete_sla = "OK"

    return {
        "action_sla":       action_sla,
        "complete_sla":     complete_sla,
        "action_due_date":  str(action_due),
        "complete_due_date":str(complete_due),
        "working_days_open":working_open,
    }

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode           TEXT,
            status            TEXT DEFAULT 'WIP',
            original_filename TEXT,
            vendor_name       TEXT,
            doc_number        TEXT,
            dices_reference   TEXT,
            po_number         TEXT,
            doc_amount        REAL,
            regions           TEXT,
            doc_type          TEXT,
            action_required   TEXT,
            action_taken      TEXT,
            category          TEXT,
            auditor           TEXT,
            comments          TEXT,
            date_ingested     TEXT,
            date_actioned     TEXT,
            days_to_action    INTEGER,
            last_updated      TEXT,
            updated_by        TEXT
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
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            field_changed  TEXT,
            old_value      TEXT,
            new_value      TEXT,
            changed_by     TEXT,
            changed_at     TEXT
        )
    """)

    # Default admin password
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
    return row["value"] == hash_password(password) if row else False

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
    query  = "SELECT * FROM transactions WHERE 1=1"
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
        if filters.get("doc_type"):
            query += " AND doc_type=?"
            params.append(filters["doc_type"])
        if filters.get("date_ingested_from"):
            query += " AND date_ingested >= ?"
            params.append(filters["date_ingested_from"])
        if filters.get("date_ingested_to"):
            query += " AND date_ingested <= ?"
            params.append(filters["date_ingested_to"])
        if filters.get("date_actioned_from"):
            query += " AND date_actioned >= ?"
            params.append(filters["date_actioned_from"])
        if filters.get("date_actioned_to"):
            query += " AND date_actioned <= ?"
            params.append(filters["date_actioned_to"])
        if filters.get("sla_breach"):
            # Only show SLA-breached open items
            today_str = str(date.today())
            action_due_cutoff   = str(add_working_days(date.today() - timedelta(days=30), 0))
            query += """ AND status NOT IN ('Completed','Closed','Rejected','Voided')
                         AND date_ingested IS NOT NULL """
        if filters.get("search"):
            s = "%" + filters["search"] + "%"
            query += " AND (barcode LIKE ? OR vendor_name LIKE ? OR doc_number LIKE ? OR po_number LIKE ?)"
            params.extend([s, s, s, s])

    query += " ORDER BY id DESC"
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    result = []
    for r in rows:
        rec = dict(r)
        # Attach SLA info to every row
        sla = get_sla_status(rec.get("date_ingested"), rec.get("status",""), rec.get("date_actioned"))
        rec.update(sla)
        # Post-filter SLA breach
        if filters and filters.get("sla_breach"):
            if sla.get("action_sla") not in ("OVERDUE","DUE TODAY") and \
               sla.get("complete_sla") not in ("OVERDUE","DUE TODAY"):
                continue
        result.append(rec)

    return result

def get_transaction_by_id(txn_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE id=?", (txn_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    rec = dict(row)
    sla = get_sla_status(rec.get("date_ingested"), rec.get("status",""), rec.get("date_actioned"))
    rec.update(sla)
    return rec

def update_transaction(txn_id, updates, updated_by):
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT * FROM transactions WHERE id=?", (txn_id,))
    old = dict(c.fetchone())

    actionable_statuses = ["Completed", "Rejected", "Closed", "Voided"]
    now      = datetime.now().strftime("%Y-%m-%d")
    now_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if "status" in updates and updates["status"] in actionable_statuses:
        if not old.get("date_actioned"):
            updates["date_actioned"] = now

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
    updates["updated_by"]   = updated_by

    set_clause = ", ".join([f"{k}=?" for k in updates.keys()])
    values = list(updates.values()) + [txn_id]
    c.execute(f"UPDATE transactions SET {set_clause} WHERE id=?", values)

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
    conn = get_conn()
    c = conn.cursor()
    now   = datetime.now().strftime("%Y-%m-%d")
    added = 0; skipped = 0

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
            if c.fetchone():
                skipped += 1
                continue

        rec = {"date_ingested": now, "status": "WIP"}
        for excel_col, db_col in col_map.items():
            if excel_col in df.columns:
                val = row.get(excel_col)
                if val is not None and str(val).strip() not in ("", "nan", "NaN"):
                    rec[db_col] = str(val).strip() if db_col != "doc_amount" else (float(val) if val else None)

        cols         = ", ".join(rec.keys())
        placeholders = ", ".join(["?"] * len(rec))
        c.execute(f"INSERT INTO transactions ({cols}) VALUES ({placeholders})", list(rec.values()))
        added += 1

    conn.commit()
    conn.close()
    return added, skipped

def get_dashboard_stats():
    conn = get_conn()
    c = conn.cursor()
    stats = {}

    c.execute("SELECT status, COUNT(*) as cnt FROM transactions GROUP BY status")
    stats["status_counts"] = {r["status"]: r["cnt"] for r in c.fetchall()}

    c.execute("""
        SELECT
            SUM(CASE WHEN days_to_action BETWEEN 0 AND 7   THEN 1 ELSE 0 END) as d0_7,
            SUM(CASE WHEN days_to_action BETWEEN 8 AND 14  THEN 1 ELSE 0 END) as d8_14,
            SUM(CASE WHEN days_to_action BETWEEN 15 AND 30 THEN 1 ELSE 0 END) as d15_30,
            SUM(CASE WHEN days_to_action > 30              THEN 1 ELSE 0 END) as d30plus
        FROM transactions
        WHERE status NOT IN ('Completed','Closed','Voided')
          AND days_to_action IS NOT NULL
    """)
    row = c.fetchone()
    stats["aging"] = dict(row) if row else {}

    c.execute("SELECT COUNT(*) as total FROM transactions")
    stats["total"] = c.fetchone()["total"]

    c.execute("SELECT AVG(days_to_action) as avg FROM transactions WHERE days_to_action IS NOT NULL")
    avg = c.fetchone()["avg"]
    stats["avg_days"] = round(avg, 1) if avg else 0

    c.execute("SELECT COUNT(*) as cnt FROM transactions WHERE status IN ('WIP','Pending Supplier')")
    stats["open"] = c.fetchone()["cnt"]

    c.execute("SELECT COUNT(*) as cnt FROM transactions WHERE status='Completed'")
    stats["completed"] = c.fetchone()["cnt"]

    c.execute("""SELECT category, COUNT(*) as cnt FROM transactions
                 WHERE category IS NOT NULL AND category != ''
                 GROUP BY category ORDER BY cnt DESC LIMIT 8""")
    stats["by_category"] = [(r["category"], r["cnt"]) for r in c.fetchall()]

    c.execute("""SELECT auditor, COUNT(*) as cnt FROM transactions
                 WHERE auditor IS NOT NULL AND auditor != ''
                 GROUP BY auditor ORDER BY cnt DESC LIMIT 10""")
    stats["by_auditor"] = [(r["auditor"], r["cnt"]) for r in c.fetchall()]

    # SLA breach counts (computed in Python)
    c.execute("SELECT date_ingested, status, date_actioned FROM transactions")
    rows = c.fetchall()
    action_breaches  = 0
    complete_breaches = 0
    for r in rows:
        sla = get_sla_status(r["date_ingested"], r["status"], r["date_actioned"])
        if sla.get("action_sla")  == "OVERDUE": action_breaches  += 1
        if sla.get("complete_sla") == "OVERDUE": complete_breaches += 1
    stats["action_breaches"]   = action_breaches
    stats["complete_breaches"] = complete_breaches

    conn.close()
    return stats

def get_audit_log(txn_id=None, limit=100):
    conn = get_conn()
    c = conn.cursor()
    if txn_id:
        c.execute("SELECT * FROM audit_log WHERE transaction_id=? ORDER BY changed_at DESC LIMIT ?",
                  (txn_id, limit))
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

def get_distinct_doc_types():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT doc_type FROM transactions WHERE doc_type IS NOT NULL AND doc_type != '' ORDER BY doc_type")
    rows = c.fetchall()
    conn.close()
    return [r["doc_type"] for r in rows]
