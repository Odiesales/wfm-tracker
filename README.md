# 📋 WFM Transaction Tracker

A secure, browser-based transaction tracking tool for the Missing PO Module.

---

## 🚀 Quick Start (Windows)

1. **Install Python 3.9+** from https://python.org (check "Add to PATH")
2. **Double-click `run.bat`** — it installs all dependencies and starts the app
3. Open your browser at **http://localhost:8501**

---

## 🔐 Login

| Role  | How to Login |
|-------|-------------|
| **Admin** | Click "Admin" → enter password (default: `admin123`) |
| **Auditor** | Click "Auditor / User" → type your name → Enter |

**Change the admin password** immediately in Settings after first login!

---

## 📋 Features

### Admin
- **Import Data** — upload your weekly Excel export (.xlsx or .csv)
- **Add New Only** mode — new rows added, existing edits preserved ✅
- **Full Replace** mode — wipe and reload (first setup only)
- Manage categories, change password
- Full audit log of all changes

### Auditors
- Browse and filter all transactions
- Edit ONLY: Status, Action Required, Action Taken, Category, Auditor, Comments, Date Actioned
- Core fields (Barcode, Vendor, Doc#, PO#, Amount, Region, etc.) are **locked read-only**
- Date Actioned auto-stamped when Status = Completed / Rejected / Closed / Voided

### Dashboard
- Status breakdown chart
- Aging buckets (0-7, 8-14, 15-30, 30+ days)
- By Category & By Auditor charts
- KPIs: Total, Open, Completed, Avg Days to Action

---

## 🌐 Sharing with your Team

To let teammates access from their own computers:
1. Run `run.bat` on your machine (it binds to `0.0.0.0`)
2. Find your IP: open Command Prompt → type `ipconfig` → look for **IPv4 Address**
3. Tell teammates to open: `http://<YOUR-IP>:8501`

---

## 📁 Files

| File | Purpose |
|------|---------|
| `app.py` | Main Streamlit application |
| `database.py` | SQLite database layer |
| `tracker.db` | Database file (auto-created on first run) |
| `requirements.txt` | Python dependencies |
| `run.bat` | Windows launcher |

---

## 🔧 Excel Import Column Mapping

Your Excel file should have these column headers (exact match):

```
Barcode | Status | Original Filename | Vendor/Supplier Name | Doc Number
DICES Reference | PO Number | Doc Amount | Regions | Doc Type
Action Required | Action Taken | Category | Auditor | Comments
```

Missing columns are simply left blank — no errors.

---

## 📦 Requirements
- Python 3.9+
- streamlit, pandas, openpyxl, matplotlib, numpy
