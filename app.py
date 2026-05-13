
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
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
STATUS_OPTIONS   = ["WIP", "Pending Supplier", "Completed", "Rejected", "Closed", "Voided"]
STATUS_COLORS    = {
    "WIP":              "#FFF9C4",
    "Pending Supplier": "#E3F2FD",
    "Completed":        "#E8F5E9",
    "Rejected":         "#FCE4EC",
    "Closed":           "#EDE7F6",
    "Voided":           "#F5F5F5",
}
WFM_GREEN  = "#00674B"
WFM_LIGHT  = "#E8F5F1"

LOCKED_FIELDS = [
    "id","barcode","original_filename","vendor_name",
    "doc_number","dices_reference","po_number",
    "doc_amount","regions","doc_type","date_ingested"
]
EDITABLE_FIELDS = [
    "status","action_required","action_taken",
    "category","auditor","comments","date_actioned"
]

# ── CUSTOM CSS ───────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #00674B, #009B6D);
        padding: 18px 24px;
        border-radius: 10px;
        margin-bottom: 20px;
        color: white;
    }
    .main-header h1 { color: white; margin: 0; font-size: 1.6rem; }
    .main-header p  { color: #c8ffe8; margin: 4px 0 0; font-size: 0.85rem; }
    .kpi-card {
        background: white;
        border-left: 5px solid #00674B;
        border-radius: 8px;
        padding: 16px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        text-align: center;
    }
    .kpi-value { font-size: 2rem; font-weight: 700; color: #00674B; }
    .kpi-label { font-size: 0.8rem; color: #666; margin-top: 4px; }
    .locked-field {
        background: #F5F5F5;
        border: 1px solid #E0E0E0;
        border-radius: 4px;
        padding: 6px 10px;
        font-size: 0.9rem;
        color: #444;
        margin-bottom: 4px;
    }
    .status-badge {
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 600;
        display: inline-block;
    }
    .admin-badge {
        background: #00674B;
        color: white;
        padding: 2px 10px;
        border-radius: 10px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .user-badge {
        background: #1F497D;
        color: white;
        padding: 2px 10px;
        border-radius: 10px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    div[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
    .stButton > button { border-radius: 6px; }
    .stTextInput > div > div > input { border-radius: 6px; }
    section[data-testid="stSidebar"] { background: #1a1a2e; }
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] label { color: #E0E0E0 !important; }
</style>
""", unsafe_allow_html=True)

# ── INIT ─────────────────────────────────────────────────
db.init_db()

if "logged_in"   not in st.session_state: st.session_state.logged_in   = False
if "is_admin"    not in st.session_state: st.session_state.is_admin    = False
if "username"    not in st.session_state: st.session_state.username    = ""
if "active_tab"  not in st.session_state: st.session_state.active_tab  = "tracker"
if "edit_id"     not in st.session_state: st.session_state.edit_id     = None

# ─────────────────────────────────────────────────────────
# LOGIN SCREEN
# ─────────────────────────────────────────────────────────
def show_login():
    col1, col2, col3 = st.columns([1,1.4,1])
    with col2:
        st.markdown("""
        <div style="background:linear-gradient(135deg,#00674B,#009B6D);
                    padding:30px;border-radius:14px;text-align:center;margin-bottom:24px;">
            <h2 style="color:white;margin:0;">📋 WFM Transaction Tracker</h2>
            <p style="color:#c8ffe8;margin:8px 0 0;">Missing PO Module</p>
        </div>
        """, unsafe_allow_html=True)

        login_type = st.radio("Login as:", ["👤  Auditor / User", "🔐  Admin"],
                               horizontal=True, label_visibility="collapsed")

        st.write("")

        if "Admin" in login_type:
            st.markdown("#### 🔐 Admin Login")
            pwd = st.text_input("Admin Password", type="password", placeholder="Enter admin password")
            if st.button("Login as Admin", use_container_width=True, type="primary"):
                if db.verify_admin(pwd):
                    st.session_state.logged_in = True
                    st.session_state.is_admin  = True
                    st.session_state.username  = "Admin"
                    st.rerun()
                else:
                    st.error("❌ Incorrect password")
            st.caption("Default password: **admin123** — change it in Admin Settings")
        else:
            st.markdown("#### 👤 Auditor Access")
            name = st.text_input("Your Name", placeholder="e.g. John Smith")
            if st.button("Enter Tracker", use_container_width=True, type="primary"):
                if name.strip():
                    st.session_state.logged_in = True
                    st.session_state.is_admin  = False
                    st.session_state.username  = name.strip()
                    st.rerun()
                else:
                    st.warning("Please enter your name")

# ─────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────
def show_sidebar():
    with st.sidebar:
        st.markdown(f"""
        <div style="text-align:center;padding:16px 0 8px;">
            <div style="font-size:1.8rem;">📋</div>
            <div style="color:white;font-weight:700;font-size:1.05rem;">WFM Tracker</div>
            <div style="margin-top:6px;">
                <span class="{"admin-badge" if st.session_state.is_admin else "user-badge"}">
                    {"🔐 Admin" if st.session_state.is_admin else f"👤 {st.session_state.username}"}
                </span>
            </div>
        </div>
        <hr style="border-color:#444;margin:12px 0;">
        """, unsafe_allow_html=True)

        st.markdown("**Navigation**")

        nav_items = [
            ("📊", "Dashboard",    "dashboard"),
            ("📋", "Tracker",      "tracker"),
        ]
        if st.session_state.is_admin:
            nav_items += [
                ("📥", "Import Data",  "import"),
                ("⚙️", "Settings",     "settings"),
                ("📜", "Audit Log",    "audit"),
            ]

        for icon, label, key in nav_items:
            active = st.session_state.active_tab == key
            btn_type = "primary" if active else "secondary"
            if st.button(f"{icon}  {label}", key=f"nav_{key}",
                         use_container_width=True, type=btn_type):
                st.session_state.active_tab = key
                st.session_state.edit_id = None
                st.rerun()

        st.markdown("---")
        if st.button("🚪  Logout", use_container_width=True):
            for k in ["logged_in","is_admin","username","active_tab","edit_id"]:
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

    # ── KPI Row ──
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-value">{stats["total"]}</div>
            <div class="kpi-label">Total Transactions</div>
        </div>""", unsafe_allow_html=True)
    with k2:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-value" style="color:#F57C00;">{stats["open"]}</div>
            <div class="kpi-label">Open (WIP + Pending)</div>
        </div>""", unsafe_allow_html=True)
    with k3:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-value" style="color:#2E7D32;">{stats["completed"]}</div>
            <div class="kpi-label">Completed</div>
        </div>""", unsafe_allow_html=True)
    with k4:
        st.markdown(f"""<div class="kpi-card">
            <div class="kpi-value" style="color:#1565C0;">{stats["avg_days"]}</div>
            <div class="kpi-label">Avg Days to Action</div>
        </div>""", unsafe_allow_html=True)

    st.write("")

    # ── Charts Row ──
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### Status Breakdown")
        sc = stats.get("status_counts", {})
        if sc:
            labels = list(sc.keys())
            values = list(sc.values())
            palette = ["#FFF176","#90CAF9","#A5D6A7","#EF9A9A","#CE93D8","#BDBDBD"]
            colors = [palette[i % len(palette)] for i in range(len(labels))]
            fig, ax = plt.subplots(figsize=(5.5, 4))
            wedges, texts, autotexts = ax.pie(
                values, labels=None, autopct="%1.0f%%",
                colors=colors, startangle=140,
                wedgeprops=dict(linewidth=1.5, edgecolor="white")
            )
            for at in autotexts:
                at.set_fontsize(9)
                at.set_fontweight("bold")
            ax.legend(wedges, [f"{l} ({v})" for l,v in zip(labels,values)],
                      loc="lower center", bbox_to_anchor=(0.5,-0.12),
                      ncol=3, fontsize=8, frameon=False)
            ax.set_facecolor("none")
            fig.patch.set_facecolor("none")
            plt.tight_layout()
            st.pyplot(fig)
            plt.close()
        else:
            st.info("No data yet")

    with c2:
        st.markdown("#### Aging — Open Items")
        aging = stats.get("aging", {})
        buckets = ["0–7 days","8–14 days","15–30 days","30+ days"]
        keys    = ["d0_7","d8_14","d15_30","d30plus"]
        values  = [aging.get(k, 0) or 0 for k in keys]
        colors  = ["#66BB6A","#FFF176","#FFB74D","#EF5350"]
        fig, ax = plt.subplots(figsize=(5.5, 4))
        bars = ax.bar(buckets, values, color=colors, edgecolor="white", linewidth=1.5, width=0.6)
        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+0.1,
                        str(val), ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax.set_ylabel("Count", fontsize=9)
        ax.set_facecolor("#FAFAFA")
        ax.spines[["top","right"]].set_visible(False)
        fig.patch.set_facecolor("none")
        plt.tight_layout()
        st.pyplot(fig)
        plt.close()

    # ── By Category & Auditor ──
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
                ax.text(w+0.1, bar.get_y()+bar.get_height()/2,
                        str(int(w)), va="center", fontsize=9)
            ax.set_facecolor("#FAFAFA")
            ax.spines[["top","right"]].set_visible(False)
            ax.invert_yaxis()
            fig.patch.set_facecolor("none")
            plt.tight_layout()
            st.pyplot(fig)
            plt.close()
        else:
            st.info("No category data yet")

    with c4:
        st.markdown("#### By Auditor")
        by_aud = stats.get("by_auditor", [])
        if by_aud:
            aud_df = pd.DataFrame(by_aud, columns=["Auditor","Count"])
            fig, ax = plt.subplots(figsize=(5.5, max(3, len(by_aud)*0.45)))
            ax.barh(aud_df["Auditor"], aud_df["Count"],
                    color="#00897B", edgecolor="white")
            for i, (_, row) in enumerate(aud_df.iterrows()):
                ax.text(row["Count"]+0.1, i, str(row["Count"]), va="center", fontsize=9)
            ax.set_facecolor("#FAFAFA")
            ax.spines[["top","right"]].set_visible(False)
            ax.invert_yaxis()
            fig.patch.set_facecolor("none")
            plt.tight_layout()
            st.pyplot(fig)
            plt.close()
        else:
            st.info("No auditor data yet")

# ─────────────────────────────────────────────────────────
# TRACKER TABLE
# ─────────────────────────────────────────────────────────
def show_tracker():
    st.markdown("""<div class="main-header">
        <h1>📋 Transaction Tracker</h1>
        <p>Browse, filter and update transactions</p>
    </div>""", unsafe_allow_html=True)

    # ── Edit modal ──
    if st.session_state.edit_id:
        show_edit_form(st.session_state.edit_id)
        return

    # ── Filters ──
    with st.expander("🔍 Filters", expanded=False):
        f1, f2, f3, f4, f5 = st.columns(5)
        f_status   = f1.selectbox("Status",   ["All"] + STATUS_OPTIONS, key="f_status")
        f_auditor  = f2.selectbox("Auditor",  ["All"] + db.get_distinct_auditors(), key="f_auditor")
        f_region   = f3.selectbox("Region",   ["All"] + db.get_distinct_regions(), key="f_region")
        f_category = f4.selectbox("Category", ["All"] + db.get_categories(), key="f_category")
        f_search   = f5.text_input("🔎 Search", placeholder="Barcode / Vendor / PO...", key="f_search")

    filters = {}
    if st.session_state.get("f_status")   != "All": filters["status"]   = st.session_state.f_status
    if st.session_state.get("f_auditor")  != "All": filters["auditor"]  = st.session_state.f_auditor
    if st.session_state.get("f_region")   != "All": filters["region"]   = st.session_state.f_region
    if st.session_state.get("f_category") != "All": filters["category"] = st.session_state.f_category
    if st.session_state.get("f_search"):             filters["search"]   = st.session_state.f_search

    txns = db.get_all_transactions(filters)

    st.markdown(f"**{len(txns)} records found**")

    if not txns:
        st.info("No transactions found. Use Import Data (Admin) to load your Excel file.")
        return

    # ── Display table ──
    display_cols = [
        "id","barcode","status","vendor_name","doc_number",
        "po_number","doc_amount","regions","doc_type",
        "action_required","action_taken","category","auditor",
        "date_ingested","date_actioned","days_to_action"
    ]
    df = pd.DataFrame(txns)
    df_display = df[[c for c in display_cols if c in df.columns]].copy()
    df_display.columns = [c.replace("_"," ").title() for c in df_display.columns]

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        height=420,
        column_config={
            "Doc Amount": st.column_config.NumberColumn(format="$%.2f"),
            "Days To Action": st.column_config.NumberColumn(format="%d days"),
            "Id": st.column_config.NumberColumn(width="small"),
        }
    )

    # ── Edit button ──
    st.write("")
    col_a, col_b, col_c = st.columns([1,1,3])
    with col_a:
        edit_id_input = st.number_input("Enter ID to edit:", min_value=1, step=1, key="edit_input")
    with col_b:
        st.write("")
        st.write("")
        if st.button("✏️ Edit Record", type="primary"):
            txn = db.get_transaction_by_id(int(edit_id_input))
            if txn:
                st.session_state.edit_id = int(edit_id_input)
                st.rerun()
            else:
                st.error("ID not found")

    # ── Export ──
    with col_c:
        st.write("")
        st.write("")
        output = io.BytesIO()
        df.to_excel(output, index=False, engine="openpyxl")
        st.download_button(
            "📥 Export to Excel",
            data=output.getvalue(),
            file_name=f"WFM_Tracker_Export_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ─────────────────────────────────────────────────────────
# EDIT FORM
# ─────────────────────────────────────────────────────────
def show_edit_form(txn_id):
    txn = db.get_transaction_by_id(txn_id)
    if not txn:
        st.error("Record not found")
        st.session_state.edit_id = None
        return

    st.markdown(f"""<div class="main-header">
        <h1>✏️ Edit Record #{txn_id}</h1>
        <p>Only editable fields are shown below. Core data is locked.</p>
    </div>""", unsafe_allow_html=True)

    if st.button("← Back to Tracker"):
        st.session_state.edit_id = None
        st.rerun()

    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### 🔒 Locked Fields (Read-Only)")
        locked_map = {
            "Barcode": txn.get("barcode",""),
            "Original Filename": txn.get("original_filename",""),
            "Vendor / Supplier": txn.get("vendor_name",""),
            "Doc Number": txn.get("doc_number",""),
            "DICES Reference": txn.get("dices_reference",""),
            "PO Number": txn.get("po_number",""),
            "Doc Amount": f"${txn.get('doc_amount') or 0:,.2f}",
            "Regions": txn.get("regions",""),
            "Doc Type": txn.get("doc_type",""),
            "Date Ingested": txn.get("date_ingested",""),
        }
        for label, val in locked_map.items():
            st.markdown(f"**{label}**")
            st.markdown(f"<div class='locked-field'>{val or '—'}</div>", unsafe_allow_html=True)

    with col_r:
        st.markdown("#### ✏️ Editable Fields")
        categories = db.get_categories()

        cur_status   = txn.get("status","WIP") or "WIP"
        cur_category = txn.get("category","") or ""
        cur_auditor  = txn.get("auditor","") or st.session_state.username

        new_status = st.selectbox("Status *",
            STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(cur_status) if cur_status in STATUS_OPTIONS else 0)

        new_action_req = st.text_area("Action Required",
            value=txn.get("action_required","") or "",
            height=80, placeholder="Describe what action is needed...")

        new_action_taken = st.text_area("Action Taken",
            value=txn.get("action_taken","") or "",
            height=80, placeholder="Describe what action was taken...")

        cat_list = [""] + categories
        cat_idx = cat_list.index(cur_category) if cur_category in cat_list else 0
        new_category = st.selectbox("Category", cat_list, index=cat_idx)

        new_auditor = st.text_input("Auditor",
            value=cur_auditor,
            placeholder="Your name")

        new_comments = st.text_area("Comments",
            value=txn.get("comments","") or "",
            height=80)

        # Date Actioned
        da_val = txn.get("date_actioned")
        if da_val:
            try:
                da_date = datetime.strptime(da_val[:10], "%Y-%m-%d").date()
            except:
                da_date = date.today()
        else:
            da_date = None

        show_date = new_status in ["Completed","Rejected","Closed","Voided"]
        if show_date:
            new_date_actioned = st.date_input(
                "Date Actioned",
                value=da_date or date.today(),
                help="Auto-set when status changes to Completed/Rejected/Closed/Voided"
            )
        else:
            new_date_actioned = da_date
            if da_date:
                st.info(f"📅 Date Actioned: {da_date}")

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
                st.success("✅ Record updated successfully!")
                import time; time.sleep(1)
                st.session_state.edit_id = None
                st.rerun()
        with s2:
            if st.button("✕ Cancel", use_container_width=True):
                st.session_state.edit_id = None
                st.rerun()

    # ── Audit history ──
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
# IMPORT DATA (Admin only)
# ─────────────────────────────────────────────────────────
def show_import():
    st.markdown("""<div class="main-header">
        <h1>📥 Import Data</h1>
        <p>Upload your weekly Excel export to refresh the tracker</p>
    </div>""", unsafe_allow_html=True)

    st.markdown("""
    ### Import Rules
    - ✅ **Add New Only** — new rows are added, existing records (by Barcode) are **preserved** with all edits intact
    - ⚠️ **Full Replace** — clears all existing data and re-imports *(use only for first load or full reset)*
    - 📅 Date Ingested is automatically stamped as **today** for new records
    """)

    uploaded = st.file_uploader(
        "Upload Excel File (.xlsx)",
        type=["xlsx","xls","csv"],
        help="Your weekly export from the source system"
    )

    if uploaded:
        try:
            if uploaded.name.endswith(".csv"):
                df = pd.read_csv(uploaded)
            else:
                df = pd.read_excel(uploaded)

            st.success(f"✅ File loaded: **{uploaded.name}** — {len(df)} rows, {len(df.columns)} columns")

            st.markdown("**Preview (first 5 rows):**")
            st.dataframe(df.head(), use_container_width=True, hide_index=True)

            st.markdown("**Column mapping detected:**")
            expected = ["Barcode","Status","Original Filename","Vendor/Supplier Name",
                        "Doc Number","DICES Reference","PO Number","Doc Amount",
                        "Regions","Doc Type","Action Required","Action Taken",
                        "Category","Auditor","Comments"]
            found   = [c for c in expected if c in df.columns or c.replace("/","/ ") in df.columns]
            missing = [c for c in expected if c not in df.columns]

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("✅ **Found columns:**")
                for col in found:
                    st.markdown(f"  - {col}")
            with c2:
                if missing:
                    st.markdown("⚠️ **Not found (will be blank):**")
                    for col in missing:
                        st.markdown(f"  - {col}")

            st.write("")
            import_mode = st.radio(
                "Import Mode:",
                ["Add New Only (recommended)", "Full Replace ⚠️"],
                index=0
            )
            mode = "add_new" if "Add New" in import_mode else "full_replace"

            if mode == "full_replace":
                st.warning("⚠️ Full Replace will delete ALL existing records and user edits!")
                confirm = st.checkbox("I understand — delete all existing data and re-import")
            else:
                confirm = True

            if st.button("🚀 Run Import", type="primary", disabled=not confirm):
                if mode == "full_replace":
                    db.delete_all_transactions()
                added, skipped = db.ingest_excel(df, mode=mode)
                st.success(f"✅ Import complete! **{added} new records added**, {skipped} existing records skipped.")
                st.balloons()

        except Exception as e:
            st.error(f"❌ Error reading file: {e}")

    st.write("")
    st.markdown("---")
    st.markdown("### 📊 Current Database Stats")
    stats = db.get_dashboard_stats()
    s1, s2, s3 = st.columns(3)
    s1.metric("Total Records", stats["total"])
    s2.metric("Open Items",    stats["open"])
    s3.metric("Completed",     stats["completed"])

# ─────────────────────────────────────────────────────────
# SETTINGS (Admin only)
# ─────────────────────────────────────────────────────────
def show_settings():
    st.markdown("""<div class="main-header">
        <h1>⚙️ Settings</h1>
        <p>Manage categories, passwords, and app configuration</p>
    </div>""", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📁 Categories", "🔐 Password"])

    with tab1:
        st.markdown("#### Manage Categories")
        cats = db.get_categories()

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Current Categories:**")
            for cat in cats:
                c1, c2 = st.columns([3,1])
                c1.write(f"• {cat}")
                if c2.button("🗑", key=f"del_{cat}", help=f"Delete {cat}"):
                    db.delete_category(cat)
                    st.rerun()

        with col_b:
            st.markdown("**Add New Category:**")
            new_cat = st.text_input("Category Name", key="new_cat_input")
            if st.button("➕ Add Category", type="primary"):
                if new_cat.strip():
                    db.add_category(new_cat.strip())
                    st.success(f"Added: {new_cat}")
                    st.rerun()

    with tab2:
        st.markdown("#### Change Admin Password")
        old_pwd = st.text_input("Current Password", type="password")
        new_pwd = st.text_input("New Password",     type="password")
        cfm_pwd = st.text_input("Confirm New Password", type="password")
        if st.button("🔐 Change Password", type="primary"):
            if not db.verify_admin(old_pwd):
                st.error("Current password is incorrect")
            elif new_pwd != cfm_pwd:
                st.error("New passwords do not match")
            elif len(new_pwd) < 6:
                st.error("Password must be at least 6 characters")
            else:
                db.change_admin_password(new_pwd)
                st.success("✅ Password updated successfully!")

# ─────────────────────────────────────────────────────────
# AUDIT LOG (Admin only)
# ─────────────────────────────────────────────────────────
def show_audit():
    st.markdown("""<div class="main-header">
        <h1>📜 Audit Log</h1>
        <p>Full history of all changes made to records</p>
    </div>""", unsafe_allow_html=True)

    log = db.get_audit_log(limit=500)
    if log:
        df = pd.DataFrame(log)
        df = df[["transaction_id","field_changed","old_value","new_value","changed_by","changed_at"]]
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
# MAIN ROUTER
# ─────────────────────────────────────────────────────────
def main():
    if not st.session_state.logged_in:
        show_login()
        return

    show_sidebar()

    tab = st.session_state.active_tab

    if tab == "dashboard": show_dashboard()
    elif tab == "tracker": show_tracker()
    elif tab == "import"  and st.session_state.is_admin: show_import()
    elif tab == "settings" and st.session_state.is_admin: show_settings()
    elif tab == "audit"   and st.session_state.is_admin: show_audit()
    else:
        st.session_state.active_tab = "tracker"
        show_tracker()

main()
