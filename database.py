import hashlib
from datetime import datetime, date, timedelta
from supabase import create_client, Client

# ── SUPABASE CONFIG ────────────────────────────────────────
SUPABASE_URL = "https://ipurotlgvljqdesrkmbx.supabase.co"
SUPABASE_KEY = "sb_publishable__jJz7Y5IQQojH6tyzoto3w_82ziqLQo"
MAX_ROWS     = 100000  # Override Supabase default 1000-row limit

_client: Client = None

def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client

# ── SLA CONSTANTS ─────────────────────────────────────────
SLA_ACTION_DAYS   = 3
SLA_COMPLETE_DAYS = 5

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def add_working_days(start_date, days):
    current = start_date
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current

def working_days_between(start_date, end_date):
    count = 0
    current = start_date
    while current < end_date:
        current += timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return count

def get_sla_status(date_ingested_str, status, date_actioned_str=None):
    if not date_ingested_str:
        return {}
    try:
        ingested = datetime.strptime(date_ingested_str[:10], "%Y-%m-%d").date()
    except:
        return {}

    today         = date.today()
    action_due    = add_working_days(ingested, SLA_ACTION_DAYS)
    complete_due  = add_working_days(ingested, SLA_COMPLETE_DAYS)
    working_open  = working_days_between(ingested, today)

    closed_statuses = ["Completed", "Closed", "Rejected", "Voided"]
    is_closed = status in closed_statuses

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

    if is_closed:
        complete_sla = "DONE"
    elif today > complete_due:
        complete_sla = "OVERDUE"
    elif today == complete_due:
        complete_sla = "DUE TODAY"
    else:
        complete_sla = "OK"

    return {
        "action_sla":        action_sla,
        "complete_sla":      complete_sla,
        "action_due_date":   str(action_due),
        "complete_due_date": str(complete_due),
        "working_days_open": working_open,
    }

def init_db():
    sb = get_client()
    try:
        res = sb.table("settings").select("*").eq("key", "admin_password").execute()
        if not res.data:
            sb.table("settings").insert({"key": "admin_password", "value": hash_password("admin123")}).execute()
    except:
        pass
    try:
        default_cats = [
            "Invoice - Regular", "Invoice - Utility", "Credit Memo",
            "Duplicate", "Missing PO", "Price Discrepancy",
            "Receiving Issue", "Other"
        ]
        for cat in default_cats:
            try:
                sb.table("categories").insert({"name": cat}).execute()
            except:
                pass
    except:
        pass

def verify_admin(password):
    try:
        sb  = get_client()
        res = sb.table("settings").select("value").eq("key", "admin_password").execute()
        if res.data:
            return res.data[0]["value"] == hash_password(password)
    except:
        pass
    return False

def change_admin_password(new_password):
    sb = get_client()
    sb.table("settings").update({"value": hash_password(new_password)}).eq("key", "admin_password").execute()

def get_categories():
    try:
        sb  = get_client()
        res = sb.table("categories").select("name").order("name").limit(MAX_ROWS).execute()
        return [r["name"] for r in res.data]
    except:
        return []

def add_category(name):
    sb = get_client()
    try:
        sb.table("categories").insert({"name": name}).execute()
    except:
        pass

def delete_category(name):
    sb = get_client()
    sb.table("categories").delete().eq("name", name).execute()

def get_all_transactions(filters=None):
    sb    = get_client()
    query = sb.table("transactions").select("*")

    if filters:
        if filters.get("status"):
            query = query.eq("status", filters["status"])
        if filters.get("auditor"):
            query = query.eq("auditor", filters["auditor"])
        if filters.get("region"):
            query = query.eq("regions", filters["region"])
        if filters.get("category"):
            query = query.eq("category", filters["category"])
        if filters.get("doc_type"):
            query = query.eq("doc_type", filters["doc_type"])
        if filters.get("date_ingested_from"):
            query = query.gte("date_ingested", filters["date_ingested_from"])
        if filters.get("date_ingested_to"):
            query = query.lte("date_ingested", filters["date_ingested_to"])
        if filters.get("date_actioned_from"):
            query = query.gte("date_actioned", filters["date_actioned_from"])
        if filters.get("date_actioned_to"):
            query = query.lte("date_actioned", filters["date_actioned_to"])
        if filters.get("search"):
            s = filters["search"]
            query = query.or_(f"barcode.ilike.%{s}%,vendor_name.ilike.%{s}%,doc_number.ilike.%{s}%,po_number.ilike.%{s}%")

    res  = query.order("id", desc=True).limit(MAX_ROWS).execute()
    rows = res.data or []

    result = []
    for rec in rows:
        sla = get_sla_status(rec.get("date_ingested"), rec.get("status", ""), rec.get("date_actioned"))
        rec.update(sla)
        if filters and filters.get("sla_breach"):
            if sla.get("action_sla") not in ("OVERDUE", "DUE TODAY") and \
               sla.get("complete_sla") not in ("OVERDUE", "DUE TODAY"):
                continue
        result.append(rec)

    return result

def get_transaction_by_id(txn_id):
    sb  = get_client()
    res = sb.table("transactions").select("*").eq("id", txn_id).execute()
    if not res.data:
        return None
    rec = res.data[0]
    sla = get_sla_status(rec.get("date_ingested"), rec.get("status", ""), rec.get("date_actioned"))
    rec.update(sla)
    return rec

def update_transaction(txn_id, updates, updated_by):
    sb  = get_client()
    res = sb.table("transactions").select("*").eq("id", txn_id).execute()
    if not res.data:
        return
    old = res.data[0]

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

    sb.table("transactions").update(updates).eq("id", txn_id).execute()

    for field, new_val in updates.items():
        if field not in ("last_updated", "updated_by"):
            old_val = old.get(field)
            if str(old_val) != str(new_val):
                sb.table("audit_log").insert({
                    "transaction_id": txn_id,
                    "field_changed":  field,
                    "old_value":      str(old_val),
                    "new_value":      str(new_val),
                    "changed_by":     updated_by,
                    "changed_at":     now_full
                }).execute()

def mass_update_transactions(txn_ids, updates, updated_by):
    for txn_id in txn_ids:
        update_transaction(txn_id, updates.copy(), updated_by)

def ingest_excel(df, mode="add_new"):
    sb      = get_client()
    now     = datetime.now().strftime("%Y-%m-%d")
    added   = 0
    skipped = 0

    col_map = {
        "Barcode":                "barcode",
        "Status":                 "status",
        "Original Filename":      "original_filename",
        "Vendor/Supplier Name":   "vendor_name",
        "Vendor / Supplier Name": "vendor_name",
        "Doc Number":             "doc_number",
        "DICES Reference":        "dices_reference",
        "PO Number":              "po_number",
        "Doc Amount":             "doc_amount",
        "Regions":                "regions",
        "Doc Type":               "doc_type",
        "Action Required":        "action_required",
        "Action Taken":           "action_taken",
        "Category":               "category",
        "Auditor":                "auditor",
        "Comments":               "comments",
    }

    existing_barcodes = set()
    if mode == "add_new":
        res = sb.table("transactions").select("barcode").limit(MAX_ROWS).execute()
        existing_barcodes = {r["barcode"] for r in (res.data or [])}

    batch = []
    for _, row in df.iterrows():
        barcode = str(row.get("Barcode", "")).strip()
        if not barcode or barcode in ("nan", "NaN", ""):
            continue

        if mode == "add_new" and barcode in existing_barcodes:
            skipped += 1
            continue

        rec = {"date_ingested": now, "status": "WIP"}
        for excel_col, db_col in col_map.items():
            if excel_col in df.columns:
                val = row.get(excel_col)
                if val is not None and str(val).strip() not in ("", "nan", "NaN"):
                    if db_col == "doc_amount":
                        try:
                            rec[db_col] = float(val)
                        except:
                            pass
                    else:
                        rec[db_col] = str(val).strip()

        batch.append(rec)
        added += 1

        if len(batch) >= 50:
            sb.table("transactions").insert(batch).execute()
            batch = []

    if batch:
        sb.table("transactions").insert(batch).execute()

    return added, skipped

def get_dashboard_stats():
    sb    = get_client()
    stats = {}

    res = sb.table("transactions").select("status").limit(MAX_ROWS).execute()
    rows = res.data or []
    status_counts = {}
    for r in rows:
        s = r["status"] or "Unknown"
        status_counts[s] = status_counts.get(s, 0) + 1
    stats["status_counts"] = status_counts
    stats["total"]     = len(rows)
    stats["open"]      = sum(v for k, v in status_counts.items() if k in ("WIP", "Pending Supplier"))
    stats["completed"] = status_counts.get("Completed", 0)

    res2 = sb.table("transactions").select(
        "date_ingested,status,date_actioned,days_to_action,category,auditor"
    ).limit(MAX_ROWS).execute()
    all_rows = res2.data or []

    days_list = [r["days_to_action"] for r in all_rows if r.get("days_to_action") is not None]
    stats["avg_days"] = round(sum(days_list) / len(days_list), 1) if days_list else 0

    aging = {"d0_7": 0, "d8_14": 0, "d15_30": 0, "d30plus": 0}
    action_breaches   = 0
    complete_breaches = 0

    for r in all_rows:
        d = r.get("days_to_action")
        if d is not None and r.get("status") not in ("Completed", "Closed", "Voided"):
            if d <= 7:    aging["d0_7"]    += 1
            elif d <= 14: aging["d8_14"]   += 1
            elif d <= 30: aging["d15_30"]  += 1
            else:         aging["d30plus"] += 1

        sla = get_sla_status(r.get("date_ingested"), r.get("status", ""), r.get("date_actioned"))
        if sla.get("action_sla")   == "OVERDUE": action_breaches   += 1
        if sla.get("complete_sla") == "OVERDUE": complete_breaches += 1

    stats["aging"]             = aging
    stats["action_breaches"]   = action_breaches
    stats["complete_breaches"] = complete_breaches

    cat_counts = {}
    for r in all_rows:
        c = r.get("category")
        if c:
            cat_counts[c] = cat_counts.get(c, 0) + 1
    stats["by_category"] = sorted(cat_counts.items(), key=lambda x: -x[1])[:8]

    aud_counts = {}
    for r in all_rows:
        a = r.get("auditor")
        if a:
            aud_counts[a] = aud_counts.get(a, 0) + 1
    stats["by_auditor"] = sorted(aud_counts.items(), key=lambda x: -x[1])[:10]

    return stats

def get_audit_log(txn_id=None, limit=100):
    sb = get_client()
    if txn_id:
        res = sb.table("audit_log").select("*").eq("transaction_id", txn_id).order("changed_at", desc=True).limit(limit).execute()
    else:
        res = sb.table("audit_log").select("*").order("changed_at", desc=True).limit(limit).execute()
    return res.data or []

def delete_all_transactions():
    sb = get_client()
    while True:
        res = sb.table("transactions").select("id").limit(500).execute()
        if not res.data:
            break
        ids = [r["id"] for r in res.data]
        sb.table("transactions").delete().in_("id", ids).execute()

def get_distinct_auditors():
    sb  = get_client()
    res = sb.table("transactions").select("auditor").limit(MAX_ROWS).execute()
    return sorted(set(r["auditor"] for r in (res.data or []) if r.get("auditor")))

def get_distinct_regions():
    sb  = get_client()
    res = sb.table("transactions").select("regions").limit(MAX_ROWS).execute()
    return sorted(set(r["regions"] for r in (res.data or []) if r.get("regions")))

def get_distinct_doc_types():
    sb  = get_client()
    res = sb.table("transactions").select("doc_type").limit(MAX_ROWS).execute()
    return sorted(set(r["doc_type"] for r in (res.data or []) if r.get("doc_type")))
