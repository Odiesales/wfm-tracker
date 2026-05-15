
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import io
from datetime import datetime, date
import database as db

# ── PAGE CONFIG ──────────────────────────────────────────
st.set_page_config(
    page_title="WFM Transaction Tracker",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CONSTANTS ────────────────────────────────────────────
STATUS_OPTIONS  = ["WIP", "Pending Supplier", "Completed", "Rejected", "Closed", "Voided"]
SLA_COLORS      = {
    "OK":        "🟢",
    "DUE TODAY": "🟡",
    "OVERDUE":   "🔴",
    "DONE":      "✅",
    "":          "—",
}

# ── CUSTOM CSS ───────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #00674B, #009B6D);
        padding: 18px 24px; border-radius: 10px;
        margin-bottom: 20px; color: white;
    }
    .main-header h1 { color: white; margin: 0; font-size: 1.6rem; }
    .main-header p  { color: #c8ffe8; margin: 4px 0 0; font-size: 0.85rem; }
    .kpi-card {
        background: white; border-left: 5px solid #00674B;
        border-radius: 8px; padding: 16px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center;
    }
    .kpi-value { font-size: 2rem; font-weight: 700; color: #00674B; }
    .kpi-label { font-size: 0.8rem; color: #666; margin-top: 4px; }
    .kpi-red   { border-left-color: #EF5350 !important; }
    .kpi-red .kpi-value { color: #EF5350 !important; }
    .kpi-amber { border-left-color: #FFB74D !important; }
    .kpi-amber .kpi-value { color: #F57C00 !important; }
    .locked-field {
        background: #F5F5F5; border: 1px solid #E0E0E0;
        border-radius: 4px; padding: 6px 10px;
        font-size: 0.9rem; color: #444; margin-bottom: 4px;
    }
    .mass-update-box {
        background: #E8F5F1; border: 2px solid #00674B;
        border-radius: 10px; padding: 16px 20px; margin-bottom: 16px;
    }
    .sla-legend {
        background: #FAFAFA; border: 1px solid #E0E0E0;
        border-radius: 8px; padding: 10px 16px; margin-bottom: 12px;
        font-size: 0.82rem;
    }
    .admin-badge { background:#00674B;color:white;padding:2px 10px;border-radius:10px;font-size:0.75rem;font-weight:600; }
    .user-badge  { background:#1F497D;color:white;padding:2px 10px;border-radius:10px;font-size:0.75rem;font-weight:600; }
    div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
    .stButton > button { border-radius: 6px; }
    section[data-testid="stSidebar"] { background: #1a1a2e; }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] label { color: #E0E0E0 !important; }
</style>
""", unsafe_allow_html=True)

# ── INIT ─────────────────────────────────────────────────
db.init_db()

defaults = {
    "logged_in": False, "is_admin": False, "username": "",
    "active_tab": "tracker", "edit_id": None,
    "selected_ids": [], "show_mass_update": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────
def show_login():
    col1, col2, col3 = st.columns([1, 1.4, 1])
    with col2:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#00674B,#009B6D);
                    padding:30px;border-radius:14px;text-align:center;margin-bottom:24px;">
            <h2 style="color:white;margin:0;">📋 WFM Transaction Tracker</h2>
            <p style="color:#c8ffe8;margin:8px 0 0;">Missing PO Module</p>
        </div>""", unsafe_allow_html=True)

        login_type = st.radio("Login as:", ["👤  Auditor / User", "🔐  Admin"],
                              horizontal=True, label_visibility="collapsed")
        st.write("")

        if "Admin" in login_type:
            st.markdown("#### 🔐 Admin Login")
            pwd = st.text_input("Admin Password", type="password")
            if st.button("Login as Admin", use_container_width=True, type="primary"):
                if db.verify_admin(pwd):
                    st.session_state.update(logged_in=True, is_admin=True, username="Admin")
                    st.rerun()
                else:
                    st.error("❌ Incorrect password")
            st.caption("Default: **admin123** — change in Settings")
        else:
            st.markdown("#### 👤 Auditor Access")
            name = st.text_input("Your Name", placeholder="e.g. John Smith")
            if st.button("Enter Tracker", use_container_width=True, type="primary"):
                if name.strip():
                    st.session_state.update(logged_in=True, is_admin=False, username=name.strip())
                    st.rerun()
                else:
                    st.warning("Please enter your name")

# ─────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────
def show_sidebar():
    with st.sidebar:
        badge = "admin-badge" if st.session_state.is_admin else "user-badge"
        label = "🔐 Admin" if st.session_state.is_admin else f"👤 {st.session_state.username}"
        st.markdown(f"""
        <div style="text-align:center;padding:16px 0 8px;">
            <div style="font-size:1.8rem;">📋</div>
            <div style="color:white;font-weight:700;font-size:1.05rem;">WFM Tracker</div>
            <div style="margin-top:6px;"><span class="{badge}">{label}</span></div>
        </div>
        <hr style="border-color:#444;margin:12px 0;">""", unsafe_allow_html=True)

        st.markdown("**Navigation**")
        nav_items = [("📊","Dashboard","dashboard"),("📋","Tracker","tracker")]
        if st.session_state.is_admin:
            nav_items += [("📥","Import Data","import"),("⚙️","Settings","settings"),("📜","Audit Log","audit")]

        for icon, label, key in nav_items:
            active = st.session_state.active_tab == key
            if st.button(f"{icon}  {label}", key=f"nav_{key}",
                         use_container_width=True, type="primary" if active else "secondary"):
                st.session_state.update(active_tab=key, edit_id=None,
                                        selected_ids=[], show_mass_update=False)
                st.rerun()

        st.markdown("---")
        if st.button("🚪  Logout", use_container_width=True):
            for k in list(defaults.keys()):
                st.session_state.pop(k, None)
            st.rerun()

# ─────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────
def show_dashboard():
    st.markdown("""<div class="main-header">
        <h1>📊 Dashboard</h1>
        <p>Real-time overview of all transactions</p>
    </div>""", unsafe_allow_html=True)

    stats = db.get_dashboard_stats()

    # ── KPI row ──
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    kpis = [
        (k1, stats["total"],             "Total Transactions", "",      ""),
        (k2, stats["open"],              "Open (WIP+Pending)", "amber", ""),
        (k3, stats["completed"],         "Completed",          "",      "color:#2E7D32"),
        (k4, stats["avg_days"],          "Avg Days to Action", "",      "color:#1565C0"),
        (k5, stats["action_breaches"],   "Action SLA Breached","red",   ""),
        (k6, stats["complete_breaches"], "Completion SLA Breached","red",""),
    ]
    for col, val, lbl, card_cls, val_style in kpis:
        with col:
            st.markdown(f"""<div class="kpi-card {f'kpi-{card_cls}' if card_cls else ''}">
                <div class="kpi-value" style="{val_style}">{val}</div>
                <div class="kpi-label">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    st.write("")

    # ── SLA info box ──
    st.markdown(f"""<div class="sla-legend">
        📏 <b>SLA Rules:</b> &nbsp;
        🟢 Action required within <b>{db.SLA_ACTION_DAYS} working days</b> of ingestion &nbsp;|&nbsp;
        🟢 Completion within <b>{db.SLA_COMPLETE_DAYS} working days</b> of ingestion &nbsp;|&nbsp;
        🟡 = Due today &nbsp; 🔴 = Overdue &nbsp; ✅ = Done
    </div>""", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Status Breakdown")
        sc = stats.get("status_counts", {})
        if sc:
            labels  = list(sc.keys()); values = list(sc.values())
            palette = ["#FFF176","#90CAF9","#A5D6A7","#EF9A9A","#CE93D8","#BDBDBD"]
            colors  = [palette[i % len(palette)] for i in range(len(labels))]
            fig, ax = plt.subplots(figsize=(5.5, 4))
            wedges, _, autotexts = ax.pie(values, labels=None, autopct="%1.0f%%",
                colors=colors, startangle=140, wedgeprops=dict(linewidth=1.5, edgecolor="white"))
            for at in autotexts: at.set_fontsize(9); at.set_fontweight("bold")
            ax.legend(wedges, [f"{l} ({v})" for l,v in zip(labels,values)],
                      loc="lower center", bbox_to_anchor=(0.5,-0.12), ncol=3, fontsize=8, frameon=False)
            ax.set_facecolor("none"); fig.patch.set_facecolor("none")
            plt.tight_layout(); st.pyplot(fig); plt.close()
        else:
            st.info("No data yet")

    with c2:
        st.markdown("#### Aging — Open Items")
        aging   = stats.get("aging", {})
        buckets = ["0-7 days","8-14 days","15-30 days","30+ days"]
        keys    = ["d0_7","d8_14","d15_30","d30plus"]
        values  = [aging.get(k, 0) or 0 for k in keys]
        colors  = ["#66BB6A","#FFF176","#FFB74D","#EF5350"]
        fig, ax = plt.subplots(figsize=(5.5, 4))
        bars = ax.bar(buckets, values, color=colors, edgecolor="white", linewidth=1.5, width=0.6)
        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.1,
                        str(val), ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_ylabel("Count", fontsize=9); ax.set_facecolor("#FAFAFA")
        ax.spines[["top","right"]].set_visible(False); fig.patch.set_facecolor("none")
        plt.tight_layout(); st.pyplot(fig); plt.close()

    c3, c4 = st.columns(2)
    with c3:
        st.markdown("#### By Category")
        by_cat = stats.get("by_category", [])
        if by_cat:
            cat_df = pd.DataFrame(by_cat, columns=["Category","Count"])
            fig, ax = plt.subplots(figsize=(5.5, max(3, len(by_cat)*0.45)))
            colors = plt.cm.Set3(np.linspace(0, 1, len(by_cat)))
            bars = ax.barh(cat_df["Category"], cat_df["Count"], color=colors, edgecolor="white")
            for bar in bars:
                w = bar.get_width()
                ax.text(w+0.1, bar.get_y()+bar.get_height()/2, str(int(w)), va="center", fontsize=9)
            ax.set_facecolor("#FAFAFA"); ax.spines[["top","right"]].set_visible(False); ax.invert_yaxis()
            fig.patch.set_facecolor("none"); plt.tight_layout(); st.pyplot(fig); plt.close()
        else:
            st.info("No category data yet")

    with c4:
        st.markdown("#### By Auditor")
        by_aud = stats.get("by_auditor", [])
        if by_aud:
            aud_df = pd.DataFrame(by_aud, columns=["Auditor","Count"])
            fig, ax = plt.subplots(figsize=(5.5, max(3, len(by_aud)*0.45)))
            ax.barh(aud_df["Auditor"], aud_df["Count"], color="#00897B", edgecolor="white")
            for i, (_, row) in enumerate(aud_df.iterrows()):
                ax.text(row["Count"]+0.1, i, str(row["Count"]), va="center", fontsize=9)
            ax.set_facecolor("#FAFAFA"); ax.spines[["top","right"]].set_visible(False); ax.invert_yaxis()
            fig.patch.set_facecolor("none"); plt.tight_layout(); st.pyplot(fig); plt.close()
        else:
            st.info("No auditor data yet")

# ─────────────────────────────────────────────────────────
# TRACKER  (checkboxes + mass update + enhanced filters + SLA)
# ─────────────────────────────────────────────────────────
def show_tracker():
    st.markdown("""<div class="main-header">
        <h1>📋 Transaction Tracker</h1>
        <p>Filter, select with checkboxes, then edit individually or mass-update</p>
    </div>""", unsafe_allow_html=True)

    if st.session_state.edit_id:
        show_edit_form(st.session_state.edit_id)
        return

    # ── SLA legend ──
    st.markdown(f"""<div class="sla-legend">
        📏 <b>SLA:</b> &nbsp;
        Action due in <b>{db.SLA_ACTION_DAYS} working days</b> &nbsp;|&nbsp;
        Completion due in <b>{db.SLA_COMPLETE_DAYS} working days</b> &nbsp;|&nbsp;
        🟢 OK &nbsp; 🟡 Due Today &nbsp; 🔴 Overdue &nbsp; ✅ Done
    </div>""", unsafe_allow_html=True)

    # ── FILTERS ──
    with st.expander("🔍 Filters", expanded=False):
        # Row 1
        r1c1, r1c2, r1c3, r1c4, r1c5 = st.columns(5)
        f_status   = r1c1.selectbox("Status",   ["All"] + STATUS_OPTIONS,             key="f_status")
        f_auditor  = r1c2.selectbox("Auditor",  ["All"] + db.get_distinct_auditors(), key="f_auditor")
        f_region   = r1c3.selectbox("Region",   ["All"] + db.get_distinct_regions(),  key="f_region")
        f_category = r1c4.selectbox("Category", ["All"] + db.get_categories(),        key="f_category")
        f_doc_type = r1c5.selectbox("Doc Type", ["All"] + db.get_distinct_doc_types(),key="f_doc_type")

        # Row 2 — date ranges + SLA + search
        r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(5)
        f_ing_from  = r2c1.date_input("Date Ingested From", value=None, key="f_ing_from")
        f_ing_to    = r2c2.date_input("Date Ingested To",   value=None, key="f_ing_to")
        f_act_from  = r2c3.date_input("Date Actioned From", value=None, key="f_act_from")
        f_act_to    = r2c4.date_input("Date Actioned To",   value=None, key="f_act_to")
        f_sla_only  = r2c5.checkbox("🔴 SLA Breached Only", key="f_sla_only")

        # Row 3 — search
        f_search = st.text_input("🔎 Search (Barcode / Vendor / Doc # / PO #)", key="f_search")

    filters = {}
    if st.session_state.get("f_status","All")   != "All": filters["status"]   = st.session_state.f_status
    if st.session_state.get("f_auditor","All")  != "All": filters["auditor"]  = st.session_state.f_auditor
    if st.session_state.get("f_region","All")   != "All": filters["region"]   = st.session_state.f_region
    if st.session_state.get("f_category","All") != "All": filters["category"] = st.session_state.f_category
    if st.session_state.get("f_doc_type","All") != "All": filters["doc_type"] = st.session_state.f_doc_type
    if st.session_state.get("f_ing_from"):  filters["date_ingested_from"] = str(st.session_state.f_ing_from)
    if st.session_state.get("f_ing_to"):    filters["date_ingested_to"]   = str(st.session_state.f_ing_to)
    if st.session_state.get("f_act_from"):  filters["date_actioned_from"] = str(st.session_state.f_act_from)
    if st.session_state.get("f_act_to"):    filters["date_actioned_to"]   = str(st.session_state.f_act_to)
    if st.session_state.get("f_sla_only"):  filters["sla_breach"] = True
    if st.session_state.get("f_search"):    filters["search"]     = st.session_state.f_search

    txns = db.get_all_transactions(filters)
    st.markdown(f"**{len(txns)} records found**")

    if not txns:
        st.info("No transactions match the current filters.")
        return

    df = pd.DataFrame(txns)

    # ── Build display df with SLA emoji columns ──
    display_cols = [
        "id","barcode","status","vendor_name","doc_number","po_number",
        "doc_amount","regions","doc_type","action_required","action_taken",
        "category","auditor","date_ingested","date_actioned","days_to_action",
        "action_sla","complete_sla","action_due_date","complete_due_date","working_days_open"
    ]
    df_display = df[[c for c in display_cols if c in df.columns]].copy()

    # Convert SLA codes to emoji
    for col in ["action_sla","complete_sla"]:
        if col in df_display.columns:
            df_display[col] = df_display[col].map(lambda x: SLA_COLORS.get(str(x), str(x)))

    df_display.insert(0, "Select", False)
    if st.session_state.selected_ids:
        df_display["Select"] = df_display["id"].isin(st.session_state.selected_ids)

    # ── Action bar ──
    sel_count = len(st.session_state.selected_ids)
    ab1, ab2, ab3, ab4 = st.columns([2, 2, 2, 4])

    with ab1:
        if st.button("☑️ Select All", use_container_width=True):
            st.session_state.selected_ids = df_display["id"].tolist()
            st.rerun()
    with ab2:
        if st.button("☐ Deselect All", use_container_width=True):
            st.session_state.selected_ids = []
            st.session_state.show_mass_update = False
            st.rerun()
    with ab3:
        if sel_count > 0:
            if st.button(f"✏️ Mass Update ({sel_count} selected)", type="primary", use_container_width=True):
                st.session_state.show_mass_update = not st.session_state.show_mass_update
                st.rerun()
        else:
            st.button("✏️ Mass Update", disabled=True, use_container_width=True,
                      help="Select at least one record first")
    with ab4:
        output = io.BytesIO()
        df.to_excel(output, index=False, engine="openpyxl")
        st.download_button("📥 Export to Excel", data=output.getvalue(),
            file_name=f"WFM_Tracker_Export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True)

    # ── Mass update panel ──
    if st.session_state.show_mass_update and sel_count > 0:
        st.markdown(f"""<div class="mass-update-box">
            <b>✏️ Mass Update — {sel_count} record(s) selected</b><br>
            <small>Only fields you fill in will be updated. Leave blank to keep existing values.</small>
        </div>""", unsafe_allow_html=True)

        categories = db.get_categories()
        mu1, mu2, mu3 = st.columns(3)

        with mu1:
            mu_status   = st.selectbox("Status",   ["— keep existing —"] + STATUS_OPTIONS, key="mu_status")
            mu_category = st.selectbox("Category", ["— keep existing —"] + categories,     key="mu_category")
        with mu2:
            mu_auditor    = st.text_input("Auditor",          placeholder="Leave blank to keep", key="mu_auditor")
            mu_action_req = st.text_area("Action Required",   placeholder="Leave blank to keep", height=80, key="mu_action_req")
        with mu3:
            mu_action_taken = st.text_area("Action Taken", placeholder="Leave blank to keep", height=80, key="mu_action_taken")
            mu_comments     = st.text_area("Comments",     placeholder="Leave blank to keep", height=80, key="mu_comments")

        mu_status_val = st.session_state.get("mu_status","— keep existing —")
        if mu_status_val in ["Completed","Rejected","Closed","Voided"]:
            mu_date_actioned = st.date_input("Date Actioned", value=date.today(), key="mu_date_actioned")
        else:
            mu_date_actioned = None

        mc1, mc2 = st.columns([1, 4])
        with mc1:
            if st.button("💾 Apply to Selected", type="primary", use_container_width=True):
                updates = {}
                if mu_status_val != "— keep existing —":
                    updates["status"] = mu_status_val
                if st.session_state.get("mu_category","— keep existing —") != "— keep existing —":
                    updates["category"] = st.session_state.mu_category
                if st.session_state.get("mu_auditor","").strip():
                    updates["auditor"] = st.session_state.mu_auditor.strip()
                if st.session_state.get("mu_action_req","").strip():
                    updates["action_required"] = st.session_state.mu_action_req.strip()
                if st.session_state.get("mu_action_taken","").strip():
                    updates["action_taken"] = st.session_state.mu_action_taken.strip()
                if st.session_state.get("mu_comments","").strip():
                    updates["comments"] = st.session_state.mu_comments.strip()
                if mu_date_actioned:
                    updates["date_actioned"] = str(mu_date_actioned)

                if not updates:
                    st.warning("⚠️ No fields filled in — nothing to update.")
                else:
                    for txn_id in st.session_state.selected_ids:
                        db.update_transaction(txn_id, updates, st.session_state.username)
                    st.success(f"✅ Updated {len(st.session_state.selected_ids)} records!")
                    st.session_state.selected_ids     = []
                    st.session_state.show_mass_update = False
                    import time; time.sleep(1)
                    st.rerun()
        with mc2:
            if st.button("✕ Cancel Mass Update", use_container_width=True):
                st.session_state.show_mass_update = False
                st.rerun()

        st.markdown("---")

    # ── Table ──
    col_cfg = {
        "Select":           st.column_config.CheckboxColumn("✓",          width="small"),
        "id":               st.column_config.NumberColumn("ID",            width="small"),
        "barcode":          st.column_config.TextColumn("Barcode"),
        "status":           st.column_config.TextColumn("Status"),
        "vendor_name":      st.column_config.TextColumn("Vendor"),
        "doc_number":       st.column_config.TextColumn("Doc #"),
        "po_number":        st.column_config.TextColumn("PO #"),
        "doc_amount":       st.column_config.NumberColumn("Amount",        format="$%.2f"),
        "regions":          st.column_config.TextColumn("Region"),
        "doc_type":         st.column_config.TextColumn("Doc Type"),
        "action_required":  st.column_config.TextColumn("Action Req."),
        "action_taken":     st.column_config.TextColumn("Action Taken"),
        "category":         st.column_config.TextColumn("Category"),
        "auditor":          st.column_config.TextColumn("Auditor"),
        "date_ingested":    st.column_config.TextColumn("Date Ingested"),
        "date_actioned":    st.column_config.TextColumn("Date Actioned"),
        "days_to_action":   st.column_config.NumberColumn("Days",          format="%d days"),
        "action_sla":       st.column_config.TextColumn("Action SLA",      width="small"),
        "complete_sla":     st.column_config.TextColumn("Completion SLA",  width="small"),
        "action_due_date":  st.column_config.TextColumn("Action Due"),
        "complete_due_date":st.column_config.TextColumn("Complete Due"),
        "working_days_open":st.column_config.NumberColumn("Working Days Open", format="%d days"),
    }

    edited = st.data_editor(
        df_display, use_container_width=True, hide_index=True, height=450,
        column_config=col_cfg,
        disabled=[c for c in df_display.columns if c != "Select"],
        key="tracker_table"
    )

    newly_selected = edited[edited["Select"] == True]["id"].tolist()
    if newly_selected != st.session_state.selected_ids:
        st.session_state.selected_ids = newly_selected
        st.rerun()

    # ── Single edit button ──
    st.write("")
    st.caption("💡 Tip: Check one record → **Edit Single Record** for full detail. "
               "Check multiple → **Mass Update** above.")

    if sel_count == 1:
        if st.button("✏️ Edit Single Record (Full Detail)", type="primary"):
            st.session_state.edit_id = st.session_state.selected_ids[0]
            st.rerun()
    elif sel_count == 0:
        st.button("✏️ Edit Single Record", disabled=True, help="Select exactly one record")
    else:
        st.button(f"✏️ Edit Single Record ({sel_count} selected — pick one)",
                  disabled=True, help="Select only one record for single edit")

# ─────────────────────────────────────────────────────────
# EDIT FORM  (single record — full detail)
# ─────────────────────────────────────────────────────────
def show_edit_form(txn_id):
    txn = db.get_transaction_by_id(txn_id)
    if not txn:
        st.error("Record not found")
        st.session_state.edit_id = None
        return

    st.markdown(f"""<div class="main-header">
        <h1>✏️ Edit Record #{txn_id}</h1>
        <p>Only editable fields shown. Core data is locked.</p>
    </div>""", unsafe_allow_html=True)

    if st.button("← Back to Tracker"):
        st.session_state.edit_id = None
        st.rerun()

    # SLA badge
    a_sla = txn.get("action_sla","")
    c_sla = txn.get("complete_sla","")
    st.markdown(f"""
    <div class="sla-legend">
        <b>SLA Status for this record:</b> &nbsp;
        Action: <b>{SLA_COLORS.get(a_sla,a_sla)} {a_sla}</b>
        (due {txn.get('action_due_date','—')}) &nbsp;|&nbsp;
        Completion: <b>{SLA_COLORS.get(c_sla,c_sla)} {c_sla}</b>
        (due {txn.get('complete_due_date','—')}) &nbsp;|&nbsp;
        Working days open: <b>{txn.get('working_days_open','—')}</b>
    </div>""", unsafe_allow_html=True)

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown("#### 🔒 Locked Fields (Read-Only)")
        locked_map = {
            "Barcode":           txn.get("barcode",""),
            "Original Filename": txn.get("original_filename",""),
            "Vendor / Supplier": txn.get("vendor_name",""),
            "Doc Number":        txn.get("doc_number",""),
            "DICES Reference":   txn.get("dices_reference",""),
            "PO Number":         txn.get("po_number",""),
            "Doc Amount":        f"${txn.get('doc_amount') or 0:,.2f}",
            "Regions":           txn.get("regions",""),
            "Doc Type":          txn.get("doc_type",""),
            "Date Ingested":     txn.get("date_ingested",""),
        }
        for label, val in locked_map.items():
            st.markdown(f"**{label}**")
            st.markdown(f"<div class='locked-field'>{val or '—'}</div>", unsafe_allow_html=True)

    with col_r:
        st.markdown("#### ✏️ Editable Fields")
        categories   = db.get_categories()
        cur_status   = txn.get("status","WIP") or "WIP"
        cur_category = txn.get("category","")  or ""
        cur_auditor  = txn.get("auditor","")   or st.session_state.username

        new_status = st.selectbox("Status *", STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(cur_status) if cur_status in STATUS_OPTIONS else 0)
        new_action_req   = st.text_area("Action Required",  value=txn.get("action_required","") or "", height=80)
        new_action_taken = st.text_area("Action Taken",     value=txn.get("action_taken","") or "",    height=80)

        cat_list  = [""] + categories
        cat_idx   = cat_list.index(cur_category) if cur_category in cat_list else 0
        new_category = st.selectbox("Category", cat_list, index=cat_idx)
        new_auditor  = st.text_input("Auditor", value=cur_auditor)
        new_comments = st.text_area("Comments", value=txn.get("comments","") or "", height=80)

        da_val = txn.get("date_actioned")
        if da_val:
            try:    da_date = datetime.strptime(da_val[:10], "%Y-%m-%d").date()
            except: da_date = date.today()
        else:
            da_date = None

        if new_status in ["Completed","Rejected","Closed","Voided"]:
            new_date_actioned = st.date_input("Date Actioned", value=da_date or date.today())
        else:
            new_date_actioned = da_date
            if da_date: st.info(f"📅 Date Actioned: {da_date}")

        st.write("")
        s1, s2 = st.columns(2)
        with s1:
            if st.button("💾 Save Changes", type="primary", use_container_width=True):
                updates = {
                    "status":          new_status,
                    "action_required": new_action_req,
                    "action_taken":    new_action_taken,
                    "category":        new_category,
                    "auditor":         new_auditor,
                    "comments":        new_comments,
                    "date_actioned":   str(new_date_actioned) if new_date_actioned else None,
                }
                db.update_transaction(txn_id, updates, st.session_state.username)
                st.success("✅ Record updated!")
                import time; time.sleep(1)
                st.session_state.edit_id = None
                st.rerun()
        with s2:
            if st.button("✕ Cancel", use_container_width=True):
                st.session_state.edit_id = None
                st.rerun()

    st.write("")
    st.markdown("#### 📜 Change History")
    log = db.get_audit_log(txn_id=txn_id, limit=20)
    if log:
        log_df = pd.DataFrame(log)[["field_changed","old_value","new_value","changed_by","changed_at"]]
        log_df.columns = ["Field","Old Value","New Value","Changed By","Timestamp"]
        st.dataframe(log_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No changes recorded yet.")

# ─────────────────────────────────────────────────────────
# IMPORT DATA
# ─────────────────────────────────────────────────────────
def show_import():
    st.markdown("""<div class="main-header">
        <h1>📥 Import Data</h1>
        <p>Upload your weekly Excel export to refresh the tracker</p>
    </div>""", unsafe_allow_html=True)

    st.markdown("""
    ### Import Rules
    - ✅ **Add New Only** — new rows added, existing records preserved with all edits intact
    - ⚠️ **Full Replace** — clears all data and re-imports *(first load or full reset only)*
    - 📅 Date Ingested auto-stamped as **today** for new records
    """)

    uploaded = st.file_uploader("Upload Excel File (.xlsx)", type=["xlsx","xls","csv"])

    if uploaded:
        try:
            if uploaded.name.endswith(".csv"):
                df = pd.read_csv(uploaded)
            else:
                df_test = pd.read_excel(uploaded, header=2)
                if "Barcode" in df_test.columns:
                    df = df_test
                else:
                    uploaded.seek(0)
                    df = pd.read_excel(uploaded)
                df = df.dropna(how="all")

            st.success(f"✅ File loaded: **{uploaded.name}** — {len(df)} rows, {len(df.columns)} columns")
            st.dataframe(df.head(), use_container_width=True, hide_index=True)

            expected = ["Barcode","Status","Original Filename","Vendor/Supplier Name",
                        "Doc Number","DICES Reference","PO Number","Doc Amount",
                        "Regions","Doc Type","Action Required","Action Taken",
                        "Category","Auditor","Comments"]
            found   = [c for c in expected if c in df.columns]
            missing = [c for c in expected if c not in df.columns]
            c1, c2  = st.columns(2)
            with c1:
                st.markdown("✅ **Found:**")
                for col in found: st.markdown(f"  - {col}")
            with c2:
                if missing:
                    st.markdown("⚠️ **Not found (blank):**")
                    for col in missing: st.markdown(f"  - {col}")

            import_mode = st.radio("Import Mode:", ["Add New Only (recommended)","Full Replace ⚠️"], index=0)
            mode = "add_new" if "Add New" in import_mode else "full_replace"

            if mode == "full_replace":
                st.warning("⚠️ Full Replace deletes ALL existing records and user edits!")
                confirm = st.checkbox("I understand — delete all existing data and re-import")
            else:
                confirm = True

            if st.button("🚀 Run Import", type="primary", disabled=not confirm):
                if mode == "full_replace":
                    db.delete_all_transactions()
                added, skipped = db.ingest_excel(df, mode=mode)
                st.success(f"✅ Import complete! **{added} added**, {skipped} skipped.")
                st.balloons()

        except Exception as e:
            st.error(f"❌ Error: {e}")

    st.markdown("---")
    stats = db.get_dashboard_stats()
    s1, s2, s3 = st.columns(3)
    s1.metric("Total Records", stats["total"])
    s2.metric("Open Items",    stats["open"])
    s3.metric("Completed",     stats["completed"])

# ─────────────────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────────────────
def show_settings():
    st.markdown("""<div class="main-header">
        <h1>⚙️ Settings</h1>
        <p>Manage categories, passwords, and SLA configuration</p>
    </div>""", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["📁 Categories", "🔐 Password", "📏 SLA Rules"])

    with tab1:
        cats = db.get_categories()
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Current Categories:**")
            for cat in cats:
                c1, c2 = st.columns([3,1])
                c1.write(f"• {cat}")
                if c2.button("🗑", key=f"del_{cat}"):
                    db.delete_category(cat); st.rerun()
        with col_b:
            st.markdown("**Add New:**")
            new_cat = st.text_input("Category Name", key="new_cat_input")
            if st.button("➕ Add", type="primary"):
                if new_cat.strip():
                    db.add_category(new_cat.strip()); st.success(f"Added: {new_cat}"); st.rerun()

    with tab2:
        old_pwd = st.text_input("Current Password",     type="password")
        new_pwd = st.text_input("New Password",         type="password")
        cfm_pwd = st.text_input("Confirm New Password", type="password")
        if st.button("🔐 Change Password", type="primary"):
            if not db.verify_admin(old_pwd):  st.error("Current password incorrect")
            elif new_pwd != cfm_pwd:          st.error("Passwords do not match")
            elif len(new_pwd) < 6:            st.error("Min 6 characters")
            else:
                db.change_admin_password(new_pwd)
                st.success("✅ Password updated!")

    with tab3:
        st.markdown("#### Current SLA Rules")
        st.info(f"""
        - ⏱️ **Action SLA:** {db.SLA_ACTION_DAYS} working days from ingestion date
        - ✅ **Completion SLA:** {db.SLA_COMPLETE_DAYS} working days from ingestion date

        To change these values, edit the constants at the top of **database.py**:
        ```
        SLA_ACTION_DAYS   = {db.SLA_ACTION_DAYS}
        SLA_COMPLETE_DAYS = {db.SLA_COMPLETE_DAYS}
        ```
        """)

# ─────────────────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────────────────
def show_audit():
    st.markdown("""<div class="main-header">
        <h1>📜 Audit Log</h1>
        <p>Full history of all changes made to records</p>
    </div>""", unsafe_allow_html=True)

    log = db.get_audit_log(limit=500)
    if log:
        df = pd.DataFrame(log)[["transaction_id","field_changed","old_value","new_value","changed_by","changed_at"]]
        df.columns = ["Record ID","Field","Old Value","New Value","Changed By","Timestamp"]
        st.dataframe(df, use_container_width=True, hide_index=True, height=500)
        out = io.BytesIO()
        df.to_excel(out, index=False)
        st.download_button("📥 Export Audit Log", out.getvalue(),
            file_name=f"AuditLog_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("No audit records yet.")

# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────
def main():
    if not st.session_state.logged_in:
        show_login(); return

    show_sidebar()
    tab = st.session_state.active_tab

    if   tab == "dashboard":                               show_dashboard()
    elif tab == "tracker":                                 show_tracker()
    elif tab == "import"   and st.session_state.is_admin: show_import()
    elif tab == "settings" and st.session_state.is_admin: show_settings()
    elif tab == "audit"    and st.session_state.is_admin: show_audit()
    else:
        st.session_state.active_tab = "tracker"; show_tracker()

main()
