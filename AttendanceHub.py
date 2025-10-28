# AttendanceHub.py
# إدارة الغيابات للمتكوّنين — تخزين محلّي (JSON) — بدون Google Sheets
# ميزات: فروع بكلمة سر + اختصاصات + مواد (ساعات/أسبوع + إجمالي ساعات)
#        متكوّنون (هاتف + هاتف الولي) + غيابات مع شهادة طبية (لا تُحتسب)
#        واتساب للمتكوّن أو الولي + تقارير
# تنبيه: كلمات سر الفروع تُقرأ من st.secrets["branch_passwords"] (مفاتيح MB/BZ)، مع افتراضيات.

import os, json, uuid
from datetime import datetime, date, timedelta
from typing import Dict, Any, List

import streamlit as st
import pandas as pd

# ================= صفحة التطبيق =================
st.set_page_config(page_title="Attendance Hub", layout="wide")
st.markdown("""
<div style="text-align:center">
  <h1>🧾 Attendance Hub — إدارة غيابات المتكوّنين</h1>
  <p>فروع بكلمة سر • اختصاصات • مواد • غيابات • واتساب</p>
</div>
<hr>
""", unsafe_allow_html=True)

# ============== تخزين محلّي ==============
ROOT = os.getcwd()
DATA_DIR = os.path.join(ROOT, "attendance_data")
DB_PATH  = os.path.join(DATA_DIR, "attendance_db.json")

def ensure_store():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "branches": ["Menzel Bourguiba", "Bizerte"],
                "specialties": [],
                "subjects": [],   # [{id,name,branch,specialty,weekly_hours,total_hours}]
                "trainees": [],   # [{id,name,phone,guardian_phone,_]()
