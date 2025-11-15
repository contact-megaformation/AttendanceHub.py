# AttendanceHub.py
# نظام حضور وغيابات للمكوّنين والمتكوّنين — تخزين SQLite — مع واتساب وتنظيم كامل
# ميزات:
# - دخول الموظفين حسب الفرع بكلمة سر (MB / Bizerte)
# - إدارة المتكوّنين (اسم، هاتف، هاتف الولي، فرع، تخصّص)
# - إدارة المواد (اسم مادة، الساعات الجملية، الساعات الأسبوعية، فرع، تخصّص اختياري)
# - تسجيل الغيابات بالساعات + "معذور" (شهادة طبية) لا تُحتسب
# - حدّ الغياب = 10% من ساعات المادة
# - تقارير لكل متكوّن/مادة، المتبقّي من الحد
# - إرسال واتساب للمتكوّن أو لوليّه برسالة جاهزة
# لا يحتاج أي تنصيب إضافي (sqlite3 مدمج مع بايثون)

import os
import sqlite3
from datetime import datetime, date
from typing import Optional

import pandas as pd
import streamlit as st

# ===================== إعداد الصفحة =====================
st.set_page_config(page_title="Attendance Hub", layout="wide")
st.markdown("""
<div style='text-align:center'>
  <h1>🗂️ Attendance Hub — نظام الغيابات (SQLite)</h1>
  <p>إدارة المتكوّنين • المواد • الغيابات • التقارير • تنبيه واتساب</p>
</div>
<hr/>
""", unsafe_allow_html=True)

# ===================== أدوات عامة =====================
DB_PATH = "attendance.db"

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) if "/" in DB_PATH else None
    return sqlite3.connect(DB_PATH, check_same_thread=False)

conn = get_conn()
c = conn.cursor()

def init_db():
    c.execute("""
    CREATE TABLE IF NOT EXISTS trainees (
        id TEXT PRIMARY KEY,
        name TEXT,
        phone TEXT,
        guardian_phone TEXT,
        branch TEXT,
        specialty TEXT,
        created_at TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id TEXT PRIMARY KEY,
        name TEXT,
        total_hours REAL,
        weekly_hours REAL,
        branch TEXT,
        specialty TEXT,
        created_at TEXT
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS absences (
        id TEXT PRIMARY KEY,
        trainee_id TEXT,
        subject_id TEXT,
        date TEXT,
        hours REAL,
        excused INTEGER,
        created_at TEXT
    )
    """)
    conn.commit()

init_db()

def uid(prefix: str) -> str:
    # ID بسيط يعتمد الوقت
    return f"{prefix}_{int(datetime.utcnow().timestamp()*1000)}"

def normalize_tn_phone(s: str) -> str:
    if not s: return ""
    digits = "".join(ch for ch in str(s) if ch.isdigit())
    if digits.startswith("216"): return digits
    if len(digits) == 8: return "216" + digits
    return digits

def wa_link(number: str, message: str) -> Optional[str]:
    import urllib.parse
    num = "".join(ch for ch in str(number) if ch.isdigit())
    if not num:
        return None
    return f"https://wa.me/{num}?text={urllib.parse.quote(message)}"

def get_branch_password(branch: str) -> str:
    # يحاول من secrets وإلا يرجع افتراضي
    try:
        m = st.secrets["branch_passwords"]
        if branch == "Menzel Bourguiba": return str(m.get("MB","MB_2025!"))
        if branch == "Bizerte": return str(m.get("BZ","BZ_2025!"))
    except Exception:
        pass
    return "MB_2025!" if branch == "Menzel Bourguiba" else "BZ_2025!"

# ===================== دخول الفرع =====================
st.sidebar.header("🔐 دخول الفرع")
branch = st.sidebar.selectbox("اختر الفرع", ["Menzel Bourguiba","Bizerte"], key="branch_select")
if f"pw_ok::{branch}" not in st.session_state:
    st.session_state[f"pw_ok::{branch}"] = False

if not st.session_state[f"pw_ok::{branch}"]:
    pw = st.sidebar.text_input("كلمة سرّ الفرع", type="password", key=f"pw_input::{branch}")
    if st.sidebar.button("دخول", key=f"btn_enter::{branch}"):
        if pw == get_branch_password(branch):
            st.session_state[f"pw_ok::{branch}"] = True
            st.sidebar.success("تم الدخول ✅")
        else:
            st.sidebar.error("كلمة سرّ غير صحيحة ❌")
    st.stop()

# مفتاح خروج
if st.sidebar.button("🚪 قفل الفرع الحالي", key=f"btn_lock::{branch}"):
    st.session_state[f"pw_ok::{branch}"] = False
    st.experimental_rerun()

# ===================== تبويبات العمل =====================
tab_t, tab_s, tab_a, tab_r = st.tabs([
    "👥 المتكوّنون", "📚 المواد", "⏱️ الغيابات", "📊 تقارير & واتساب"
])

# ===================== وظائف قاعدة البيانات =====================
def df_sql(query: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(query, conn, params=params)

def exec_sql(query: str, params: tuple = ()):
    c.execute(query, params)
    conn.commit()

# ===================== المتكوّنون =====================
with tab_t:
    st.subheader("إدارة المتكوّنين")

    # إضافة متكوّن
    with st.expander("➕ إضافة متكوّن", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            t_name = st.text_input("الاسم واللقب", key="t_name")
            t_phone = st.text_input("هاتف المتكوّن", key="t_phone")
        with col2:
            t_guard = st.text_input("هاتف الولي", key="t_guard")
            t_spec = st.text_input("التخصّص (اختياري)", key="t_spec")
        with col3:
            st.info(f"الفرع: **{branch}**")
            btn_add_t = st.button("حفظ المتكوّن", key="btn_add_trainee")

        if btn_add_t:
            if not t_name.strip():
                st.error("الاسم مطلوب.")
            else:
                _id = uid("T")
                exec_sql(
                    "INSERT INTO trainees (id, name, phone, guardian_phone, branch, specialty, created_at) VALUES (?,?,?,?,?,?,?)",
                    (_id, t_name.strip(), normalize_tn_phone(t_phone), normalize_tn_phone(t_guard), branch, t_spec.strip(), datetime.utcnow().isoformat())
                )
                st.success("تمت إضافة المتكوّن ✅")

    # قائمة المتكوّنين + حذف
    df_t = df_sql("SELECT * FROM trainees WHERE branch=? ORDER BY created_at DESC", (branch,))
    if df_t.empty:
        st.info("لا يوجد متكوّنون بعد في هذا الفرع.")
    else:
        st.markdown("#### قائمة المتكوّنين")
        show_t = df_t.copy()
        show_t["created_at"] = pd.to_datetime(show_t["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(show_t[["name","phone","guardian_phone","specialty","created_at"]], use_container_width=True, height=350)

        col_del1, col_del2 = st.columns(2)
        with col_del1:
            t_pick_del = st.selectbox("اختر متكوّن للحذف", ["—"] + show_t["name"].tolist(), key="t_pick_del")
        with col_del2:
            if st.button("🗑️ حذف المتكوّن المختار", key="btn_del_trainee") and t_pick_del != "—":
                row = df_t[df_t["name"]==t_pick_del].iloc[0]
                # حذف الغيابات المرتبطة أيضًا
                exec_sql("DELETE FROM absences WHERE trainee_id=?", (row["id"],))
                exec_sql("DELETE FROM trainees WHERE id=?", (row["id"],))
                st.success("تم الحذف ✅")
                st.experimental_rerun()

# ===================== المواد =====================
with tab_s:
    st.subheader("إدارة المواد (حسب الفرع واختياريًا حسب التخصّص)")
    with st.expander("➕ إضافة مادة", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            s_name = st.text_input("اسم المادة", key="s_name")
            s_total = st.number_input("إجمالي الساعات (Total)", min_value=0.0, step=1.0, key="s_total")
        with col2:
            s_weekly = st.number_input("الساعات الأسبوعية", min_value=0.0, step=0.5, key="s_weekly")
            s_spec = st.text_input("التخصّص (اختياري)", key="s_spec")
        with col3:
            st.info(f"الفرع: **{branch}**")
            btn_add_s = st.button("حفظ المادة", key="btn_add_subject")
        if btn_add_s:
            if not s_name.strip() or s_total <= 0:
                st.error("اسم المادة وإجمالي الساعات مطلوبان.")
            else:
                _id = uid("S")
                exec_sql(
                    "INSERT INTO subjects (id, name, total_hours, weekly_hours, branch, specialty, created_at) VALUES (?,?,?,?,?,?,?)",
                    (_id, s_name.strip(), float(s_total), float(s_weekly), branch, s_spec.strip(), datetime.utcnow().isoformat())
                )
                st.success("تمت إضافة المادة ✅")

    df_s = df_sql("SELECT * FROM subjects WHERE branch=? ORDER BY created_at DESC", (branch,))
    if df_s.empty:
        st.info("لا توجد مواد بعد في هذا الفرع.")
    else:
        st.markdown("#### قائمة المواد")
        show_s = df_s.copy()
        show_s["created_at"] = pd.to_datetime(show_s["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(show_s[["name","total_hours","weekly_hours","specialty","created_at"]], use_container_width=True, height=350)

# ===================== الغيابات =====================
with tab_a:
    st.subheader("تسجيل الغيابات")
    # فلترة بالتخصّص
    df_t = df_sql("SELECT * FROM trainees WHERE branch=? ORDER BY name ASC", (branch,))
    df_s = df_sql("SELECT * FROM subjects WHERE branch=? ORDER BY name ASC", (branch,))

    colf1, colf2 = st.columns(2)
    with colf1:
        all_specs = ["— الكل —"] + sorted([x for x in df_t["specialty"].dropna().unique() if str(x).strip()!=""])
        spec_filter = st.selectbox("فلتر حسب التخصّص", all_specs, key="spec_filter_abs")
    with colf2:
        st.caption("اختَر تخصّصًا لتقليص القائمة.")

    if spec_filter != "— الكل —":
        df_t = df_t[df_t["specialty"].fillna("") == spec_filter]
        df_s = df_s[df_s["specialty"].fillna("") == spec_filter]

    # اختيار المتكوّن ثم المادة
    t_options = ["— اختر متكوّن —"] + df_t["name"].tolist()
    t_pick = st.selectbox("المتكوّن", t_options, key="t_pick_abs")
    if t_pick == "— اختر متكوّن —":
        st.info("اختَر متكوّن أولًا.")
    else:
        trainee_row = df_t[df_t["name"]==t_pick].iloc[0]
        # المواد المتاحة (نفس الفرع + نفس التخصّص أو فارغة)
        subj_df = df_s.copy()
        # لو ما ثماش مواد بعد التخصيص، نعرض كل مواد الفرع
        if subj_df.empty:
            subj_df = df_sql("SELECT * FROM subjects WHERE branch=? ORDER BY name ASC", (branch,))
        s_options = ["— اختر مادة —"] + subj_df["name"].tolist()
        s_pick = st.selectbox("المادة", s_options, key="s_pick_abs")
        if s_pick == "— اختر مادة —":
            st.info("اختَر مادة.")
        else:
            subject_row = subj_df[subj_df["name"]==s_pick].iloc[0]

            # واجهة إضافة غياب
            with st.form("add_absence_form"):
                colA, colB, colC = st.columns(3)
                with colA:
                    abs_date = st.date_input("تاريخ الغياب", value=date.today(), key="abs_date")
                with colB:
                    abs_hours = st.number_input("ساعات الغياب", min_value=0.0, step=0.5, key="abs_hours")
                with colC:
                    abs_excused = st.checkbox("معذور (شهادة طبية)", value=False, key="abs_excused")

                btn_add_abs = st.form_submit_button("➕ تسجيل الغياب")
            if btn_add_abs:
                if abs_hours <= 0:
                    st.error("ساعات الغياب يجب أن تكون > 0.")
                else:
                    exec_sql(
                        "INSERT INTO absences (id, trainee_id, subject_id, date, hours, excused, created_at) VALUES (?,?,?,?,?,?,?)",
                        (uid("A"), trainee_row["id"], subject_row["id"], abs_date.isoformat(), float(abs_hours), 1 if abs_excused else 0, datetime.utcnow().isoformat())
                    )
                    st.success("تم التسجيل ✅")

            # جدول الغيابات للمتكوّن/المادة + إمكانيات تعديل/حذف
            df_a = df_sql("""
                SELECT a.id, a.date, a.hours, a.excused, s.name AS subject_name
                FROM absences a
                JOIN subjects s ON s.id = a.subject_id
                WHERE a.trainee_id=? AND a.subject_id=?
                ORDER BY a.date DESC
            """, (trainee_row["id"], subject_row["id"]))
            st.markdown("#### سجّل الغيابات (هذه المادة)")
            if df_a.empty:
                st.info("لا توجد غيابات مسجّلة بعد لهذه المادة.")
            else:
                show_a = df_a.copy()
                show_a["date"] = pd.to_datetime(show_a["date"]).dt.strftime("%Y-%m-%d")
                show_a["معذور؟"] = show_a["excused"].apply(lambda x: "نعم" if int(x)==1 else "لا")
                st.dataframe(show_a[["date","hours","معذور؟"]], use_container_width=True, height=260)

                colE1, colE2, colE3 = st.columns(3)
                with colE1:
                    # تغيير معذور/غير معذور
                    abs_ids = ["—"] + show_a["id"].tolist()
                    abs_change = st.selectbox("اختر غياب لتغيير حالته (معذور/غير معذور)", abs_ids, key="abs_change")
                    if st.button("تبديل الحالة", key="btn_toggle_excused") and abs_change != "—":
                        row = df_a[df_a["id"]==abs_change].iloc[0]
                        new_val = 0 if int(row["excused"])==1 else 1
                        exec_sql("UPDATE absences SET excused=? WHERE id=?", (new_val, abs_change))
                        st.success("تم التبديل ✅")
                        st.experimental_rerun()
                with colE2:
                    abs_del = st.selectbox("اختر غياب للحذف", abs_ids, key="abs_del")
                    if st.button("🗑️ حذف الغياب", key="btn_del_abs") and abs_del != "—":
                        exec_sql("DELETE FROM absences WHERE id=?", (abs_del,))
                        st.success("تم الحذف ✅")
                        st.experimental_rerun()
                with colE3:
                    st.caption("يمكنك تعديل حالة الغياب إذا جاب شهادة طبية (لا يُحتسب).")

# ===================== التقارير & واتساب =====================
with tab_r:
    st.subheader("تقارير حسب التخصّص ← المتكوّن ← المادة")
    df_t = df_sql("SELECT * FROM trainees WHERE branch=? ORDER BY name ASC", (branch,))
    df_s = df_sql("SELECT * FROM subjects WHERE branch=? ORDER BY name ASC", (branch,))

    colr1, colr2, colr3 = st.columns(3)
    with colr1:
        specs = ["— الكل —"] + sorted([x for x in df_t["specialty"].dropna().unique() if str(x).strip()!=""])
        spec_r = st.selectbox("التخصّص", specs, key="spec_r")
        df_t_f = df_t.copy()
        df_s_f = df_s.copy()
        if spec_r != "— الكل —":
            df_t_f = df_t_f[df_t_f["specialty"].fillna("")==spec_r]
            df_s_f = df_s_f[df_s_f["specialty"].fillna("")==spec_r]
    with colr2:
        t_opts = ["— اختر متكوّن —"] + df_t_f["name"].tolist()
        t_r = st.selectbox("المتكوّن", t_opts, key="t_r")
    with colr3:
        if t_r == "— اختر متكوّن —":
            s_opts = ["—"]
        else:
            s_opts = ["— اختر مادة —"] + df_s_f["name"].tolist()
        s_r = st.selectbox("المادة", s_opts, key="s_r")

    if t_r != "— اختر متكوّن —" and s_r != "— اختر مادة —":
        tr_row = df_t[df_t["name"]==t_r].iloc[0]
        sb_row = df_s[df_s["name"]==s_r].iloc[0]

        # حسابات الحد والمتبقّي
        total_hours = float(sb_row["total_hours"] or 0.0)
        limit = round(0.10 * total_hours, 2)  # 10%
        df_a_all = df_sql("""
            SELECT hours, excused FROM absences
            WHERE trainee_id=? AND subject_id=?
        """, (tr_row["id"], sb_row["id"]))
        taken = float(df_a_all.loc[df_a_all["excused"]==0,"hours"].sum()) if not df_a_all.empty else 0.0
        remaining = max(0.0, limit - taken)

        cM1, cM2, cM3, cM4 = st.columns(4)
        cM1.metric("إجمالي ساعات المادة", f"{total_hours:.2f}")
        cM2.metric("حدّ الغياب (10%)", f"{limit:.2f}")
        cM3.metric("غياب محتسب", f"{taken:.2f}")
        cM4.metric("متبقّي", f"{remaining:.2f}")

        # جدول مفصّل لكل الغيابات للمادة
        df_det = df_sql("""
            SELECT date, hours, excused FROM absences
            WHERE trainee_id=? AND subject_id=?
            ORDER BY date DESC
        """, (tr_row["id"], sb_row["id"]))
        if df_det.empty:
            st.info("لا توجد غيابات لهذا المتكوّن في هذه المادة.")
        else:
            det = df_det.copy()
            det["date"] = pd.to_datetime(det["date"]).dt.strftime("%Y-%m-%d")
            det["معذور؟"] = det["excused"].apply(lambda x: "نعم" if int(x)==1 else "لا")
            st.dataframe(det[["date","hours","معذور؟"]], use_container_width=True, height=260)

        # رسالة واتساب
        st.markdown("#### 💬 إرسال واتساب")
        default_msg = (
            f"سلام {tr_row['name']} 👋\n"
            f"بخصوص مادة: {s_r}\n"
            f"- إجمالي الساعات: {total_hours:.2f}\n"
            f"- الحد الأقصى للغياب (10%): {limit:.2f}\n"
            f"- الغياب المحتسب: {taken:.2f}\n"
            f"- المتبقّي: {remaining:.2f}\n"
            f"الرجاء الانضباط في الحضور 🙏"
        )
        msg = st.text_area("نص الرسالة", value=default_msg, key="wa_msg_report")
        target = st.radio("المرسل إليه", ["المتكوّن","الولي"], horizontal=True, key="wa_target_report")
        phone_to = normalize_tn_phone(tr_row["phone"] if target=="المتكوّن" else tr_row["guardian_phone"])
        link = wa_link(phone_to, msg) if phone_to else None
        if not phone_to:
            st.warning("لا يوجد رقم هاتف صالح للطرف المختار.")
        elif link and st.button("📲 فتح واتساب", key="btn_wa_report"):
            st.markdown(f"[افتح المحادثة الآن]({link})")

    st.markdown("---")
    # تقرير إجمالي: لكل متكوّن/مادة (نفس الفرع وربما تخصص معيّن)
    st.subheader("تقرير إجمالي — متكوّن × مادة (في هذا الفرع)")
    df_t_all = df_sql("SELECT * FROM trainees WHERE branch=?", (branch,))
    df_s_all = df_sql("SELECT * FROM subjects WHERE branch=?", (branch,))
    if spec_r != "— الكل —":
        df_t_all = df_t_all[df_t_all["specialty"].fillna("")==spec_r]
        df_s_all = df_s_all[df_s_all["specialty"].fillna("")==spec_r]

    rows = []
    for _, tr in df_t_all.iterrows():
        for _, sb in df_s_all.iterrows():
            total = float(sb["total_hours"] or 0.0)
            lim = round(0.10 * total, 2)
            df_abs = df_sql("SELECT hours, excused FROM absences WHERE trainee_id=? AND subject_id=?", (tr["id"], sb["id"]))
            taken = float(df_abs.loc[df_abs["excused"]==0,"hours"].sum()) if not df_abs.empty else 0.0
            remaining = max(0.0, lim - taken)
            rows.append({
                "المتكوّن": tr["name"],
                "التخصّص": tr.get("specialty","") or "",
                "المادة": sb["name"],
                "ساعات المادة": total,
                "حد 10%": lim,
                "غياب محتسب": taken,
                "متبقّي": remaining
            })
    if rows:
        df_report = pd.DataFrame(rows)
        st.dataframe(df_report.sort_values(["المتكوّن","المادة"]), use_container_width=True, height=320)
    else:
        st.info("لا توجد بيانات كافية للتقرير.")

# =============== ملاحظات تشغيلية ===============
# - لتغيير كلمات سر الفروع، استعمل st.secrets:
#   [branch_passwords]
#   MB="mb_2025!"
#   BZ="bz_2025!"
# - لتبديل نسبة 10%، يمكنك تعديل السطر: limit = round(0.10 * total_hours, 2)
# - الهواتف تُطبّع إلى صيغة 216XXXXXXXX (لو دخل رقم 8 خانات).
# - التطبيق يحفظ قاعدة البيانات في ملف attendance.db محليًا.
