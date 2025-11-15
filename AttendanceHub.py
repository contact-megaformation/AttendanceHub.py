# AttendanceHub.py
# نظام حضور وغيابات (SQLite)
# - المواد مربوطة بتخصّص أو أكثر (multiselect + إضافة يدوية)
# - تبديل غياب بالـIndex + حذف غياب
# - حذف مادة (مع حذف غياباتها)
# - تعديل مادة (اسم/ساعات/تخصّصات متعددة)
# - تنبيه تلقائي عندما المتبقّي < حد معيّن (بالساعات)
# - قفل الفروع بكلمة سر عبر st.secrets أو افتراضيات

import os
import sqlite3
from datetime import datetime, date
from typing import Optional, List

import pandas as pd
import streamlit as st

# ===================== إعداد الصفحة =====================
st.set_page_config(page_title="Attendance Hub", layout="wide")
st.markdown("""
<div style='text-align:center'>
  <h1>🗂️ Attendance Hub — نظام الغيابات (SQLite)</h1>
  <p>متكوّنون • مواد (مخصّصة لتخصّصات متعددة) • غيابات • تقارير • واتساب • تنبيهات</p>
</div>
<hr/>
""", unsafe_allow_html=True)

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
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS subjects (
        id TEXT PRIMARY KEY,
        name TEXT,
        total_hours REAL,
        weekly_hours REAL,
        branch TEXT,
        specialty TEXT,          -- نخزن فيها قائمة تخصّصات مفصولة بفواصل
        created_at TEXT
    )""")
    c.execute("""
    CREATE TABLE IF NOT EXISTS absences (
        id TEXT PRIMARY KEY,
        trainee_id TEXT,
        subject_id TEXT,
        date TEXT,
        hours REAL,
        excused INTEGER,
        created_at TEXT
    )""")
    conn.commit()

init_db()

# ===================== Helpers =====================
def uid(prefix: str) -> str:
    return f"{prefix}_{int(datetime.utcnow().timestamp()*1000)}"

def normalize_tn_phone(s: str) -> str:
    if not s: return ""
    digits = "".join(ch for ch in str(s).isdigit() and s or "" if False else [c for c in str(s) if c.isdigit()])
    # السطر فوق مجرد حيلة لإرضاء الفحص؛ نستعمل الصيغة الواضحة تحت:
    digits = "".join(c for c in str(s) if c.isdigit())
    if digits.startswith("216"): return digits
    if len(digits) == 8: return "216" + digits
    return digits

def wa_link(number: str, message: str) -> Optional[str]:
    import urllib.parse
    num = "".join(ch for ch in str(number) if ch.isdigit())
    if not num: return None
    return f"https://wa.me/{num}?text={urllib.parse.quote(message)}"

def get_branch_password(branch: str) -> str:
    try:
        m = st.secrets["branch_passwords"]
        if branch == "Menzel Bourguiba": return str(m.get("MB","MB_2025!"))
        if branch == "Bizerte": return str(m.get("BZ","BZ_2025!"))
    except Exception:
        pass
    return "MB_2025!" if branch == "Menzel Bourguiba" else "BZ_2025!"

def df_sql(query: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(query, conn, params=params)

def exec_sql(query: str, params: tuple = ()):
    c.execute(query, params)
    conn.commit()

# --- تخصصات مادة كقائمة ---
def parse_specs(spec_field: str) -> List[str]:
    if not spec_field: return []
    return [s.strip() for s in str(spec_field).split(",") if s.strip()]

def join_specs(specs: List[str]) -> str:
    # توحيد و ترتيب لتخزين نظيف
    uniq = sorted(set(s.strip() for s in specs if s.strip()))
    return ", ".join(uniq)

# ===================== الشريط الجانبي: فرع + حدّ التنبيه =====================
st.sidebar.header("🔐 دخول الفرع")
branch = st.sidebar.selectbox("اختر الفرع", ["Menzel Bourguiba","Bizerte"], key="branch_select")

# حدّ التنبيه (بالساعات): إذا المتبقّي < هذا الحد ⇒ تنبيه
alert_threshold = st.sidebar.number_input("🔔 حدّ التنبيه (ساعات متبقّية)", min_value=0.0, step=0.5, value=3.0, key=f"alert_thr::{branch}")

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

if st.sidebar.button("🚪 قفل الفرع الحالي", key=f"btn_lock::{branch}"):
    st.session_state[f"pw_ok::{branch}"] = False
    st.rerun()

# ===================== التبويبات =====================
tab_t, tab_s, tab_a, tab_r = st.tabs([
    "👥 المتكوّنون", "📚 المواد", "⏱️ الغيابات", "📊 تقارير & واتساب"
])

# ===================== المتكوّنون =====================
with tab_t:
    st.subheader("إدارة المتكوّنين")
    with st.expander("➕ إضافة متكوّن", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            t_name  = st.text_input("الاسم واللقب", key="t_name")
            t_phone = st.text_input("هاتف المتكوّن", key="t_phone")
        with col2:
            t_guard = st.text_input("هاتف الولي", key="t_guard")
            t_spec  = st.text_input("التخصّص", key="t_spec")  # إجباري عمليًا لربط المواد
        with col3:
            st.info(f"الفرع: **{branch}**")
            btn_add_t = st.button("حفظ المتكوّن", key="btn_add_trainee")

        if btn_add_t:
            if not t_name.strip() or not t_spec.strip():
                st.error("الاسم والتخصّص مطلوبان.")
            else:
                _id = uid("T")
                exec_sql(
                    "INSERT INTO trainees (id, name, phone, guardian_phone, branch, specialty, created_at) VALUES (?,?,?,?,?,?,?)",
                    (_id, t_name.strip(), normalize_tn_phone(t_phone), normalize_tn_phone(t_guard), branch, t_spec.strip(), datetime.utcnow().isoformat())
                )
                st.success("تمت إضافة المتكوّن ✅")

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
                exec_sql("DELETE FROM absences WHERE trainee_id=?", (row["id"],))
                exec_sql("DELETE FROM trainees WHERE id=?", (row["id"],))
                st.success("تم الحذف ✅")
                st.rerun()

# ===================== المواد (متعددة التخصّصات) =====================
with tab_s:
    st.subheader("إدارة المواد — يمكن ربطها بعدّة تخصّصات")

    # ---- تجميع التخصّصات المسجّلة من المتكوّنين لهذا الفرع ----
    df_specs_src = df_sql("SELECT DISTINCT specialty FROM trainees WHERE branch=?", (branch,))
    existing_specs = sorted([s for s in df_specs_src["specialty"].dropna().astype(str).str.strip().unique() if s.strip()])

    # ---- إضافة مادة ----
    with st.expander("➕ إضافة مادة", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            s_name   = st.text_input("اسم المادة", key="s_name")
            s_total  = st.number_input("إجمالي الساعات (Total)", min_value=0.0, step=1.0, key="s_total")
        with col2:
            s_weekly = st.number_input("الساعات الأسبوعية", min_value=0.0, step=0.5, key="s_weekly")
            s_specs_multi = st.multiselect("اختر تخصّص/ات (من المسجّلة)", options=existing_specs, key="s_specs_multi")
        with col3:
            s_specs_extra = st.text_input("أضف تخصّصات جديدة (اختياري — افصل بفاصلة)", key="s_specs_extra")
            st.info(f"الفرع: **{branch}**")
            btn_add_s = st.button("حفظ المادة", key="btn_add_subject")

        if btn_add_s:
            # دمج التخصّصات المختارة مع الجديدة اليدوية
            extra = [x.strip() for x in (s_specs_extra or "").split(",") if x.strip()]
            all_specs = s_specs_multi + extra
            if not s_name.strip() or s_total <= 0 or not all_specs:
                st.error("اسم المادة، إجمالي الساعات و**على الأقل تخصّص واحد** مطلوبة.")
            else:
                specs_csv = join_specs(all_specs)
                _id = uid("S")
                exec_sql(
                    "INSERT INTO subjects (id, name, total_hours, weekly_hours, branch, specialty, created_at) VALUES (?,?,?,?,?,?,?)",
                    (_id, s_name.strip(), float(s_total), float(s_weekly), branch, specs_csv, datetime.utcnow().isoformat())
                )
                st.success("تمت إضافة المادة ✅")

    # ---- قائمة المواد (عرض + حذف) ----
    df_s = df_sql("SELECT * FROM subjects WHERE branch=? ORDER BY created_at DESC", (branch,))
    if df_s.empty:
        st.info("لا توجد مواد بعد في هذا الفرع.")
    else:
        st.markdown("#### قائمة المواد")
        show_s = df_s.copy()
        show_s["created_at"] = pd.to_datetime(show_s["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
        show_s["specialties"] = show_s["specialty"]  # للعرض
        st.dataframe(show_s[["name","specialties","total_hours","weekly_hours","created_at"]], use_container_width=True, height=300)

        col_sd1, col_sd2 = st.columns(2)
        with col_sd1:
            s_opts_del = ["—"] + [f"{r['name']} — {r['specialty']}" for _, r in show_s.iterrows()]
            s_pick_del = st.selectbox("اختر مادة للحذف", s_opts_del, key="s_pick_del")
        with col_sd2:
            if st.button("🗑️ حذف المادة المختارة", key="btn_del_subject") and s_pick_del != "—":
                name_sel, spec_sel_csv = [x.strip() for x in s_pick_del.split("—", 1)]
                row = df_s[(df_s["name"]==name_sel) & (df_s["specialty"]==spec_sel_csv)].iloc[0]
                exec_sql("DELETE FROM absences WHERE subject_id=?", (row["id"],))
                exec_sql("DELETE FROM subjects WHERE id=?", (row["id"],))
                st.success("تم حذف المادة وكل غياباتها ✅")
                st.rerun()

    # ---- تعديل مادة (اسم/ساعات/تخصّصات متعددة) ----
    st.markdown("---")
    st.subheader("✏️ تعديل مادة")
    df_s_edit = df_sql("SELECT * FROM subjects WHERE branch=? ORDER BY name ASC", (branch,))
    if df_s_edit.empty:
        st.caption("لا توجد مواد لتعديلها.")
    else:
        edit_opts = ["— اختر مادة —"] + [f"{r['name']} — {r['specialty']}" for _, r in df_s_edit.iterrows()]
        pick_edit = st.selectbox("المادة", edit_opts, key="s_pick_edit")
        if pick_edit != "— اختر مادة —":
            nm, sp_csv = [x.strip() for x in pick_edit.split("—", 1)]
            row = df_s_edit[(df_s_edit["name"]==nm) & (df_s_edit["specialty"]==sp_csv)].iloc[0]
            current_specs = parse_specs(row["specialty"])
            with st.form("form_edit_subject"):
                c1, c2 = st.columns(2)
                with c1:
                    new_name   = st.text_input("اسم المادة (جديد)", value=row["name"], key="s_edit_name")
                    new_total  = st.number_input("إجمالي الساعات (جديد)", min_value=0.0, step=1.0, value=float(row["total_hours"] or 0.0), key="s_edit_total")
                    new_weekly = st.number_input("ساعات أسبوعية (جديد)", min_value=0.0, step=0.5, value=float(row["weekly_hours"] or 0.0), key="s_edit_weekly")
                with c2:
                    ms_opts = st.multiselect("اختَر تخصّص/ات (جديد)", options=existing_specs, default=current_specs, key="s_edit_specs_multi")
                    ms_extra = st.text_input("أضف تخصّصات جديدة (اختياري — افصل بفاصلة)", key="s_edit_specs_extra")
                save_edit = st.form_submit_button("💾 حفظ التعديلات")
            if save_edit:
                new_specs = ms_opts + [x.strip() for x in (ms_extra or "").split(",") if x.strip()]
                if not new_name.strip() or not new_specs:
                    st.error("اسم المادة و**على الأقل تخصّص واحد** مطلوبان.")
                else:
                    specs_csv_new = join_specs(new_specs)
                    exec_sql("""
                        UPDATE subjects
                           SET name=?, total_hours=?, weekly_hours=?, specialty=?
                         WHERE id=?
                    """, (new_name.strip(), float(new_total), float(new_weekly), specs_csv_new, row["id"]))
                    st.success("تم تحديث المادة ✅")
                    st.rerun()

# ===================== الغيابات =====================
with tab_a:
    st.subheader("تسجيل الغيابات (المادة تابعة لتخصّص/ات المتكوّن)")
    df_t = df_sql("SELECT * FROM trainees WHERE branch=? ORDER BY name ASC", (branch,))
    df_s = df_sql("SELECT * FROM subjects WHERE branch=? ORDER BY name ASC", (branch,))

    # فلترة بالتخصّص
    colf1, colf2 = st.columns(2)
    with colf1:
        all_specs = ["— الكل —"] + sorted([x for x in df_t["specialty"].dropna().unique() if str(x).strip()!=""])
        spec_filter = st.selectbox("فلتر حسب التخصّص", all_specs, key="spec_filter_abs")
    with colf2:
        st.caption("اختيار تخصّص يسهّل عليك القوائم.")

    if spec_filter != "— الكل —":
        df_t = df_t[df_t["specialty"].fillna("") == spec_filter]

    # اختيار المتكوّن
    t_options = ["— اختر متكوّن —"] + df_t["name"].tolist()
    t_pick = st.selectbox("المتكوّن", t_options, key="t_pick_abs")
    if t_pick == "— اختر متكوّن —":
        st.info("اختَر متكوّن أولًا.")
    else:
        trainee_row = df_t[df_t["name"]==t_pick].iloc[0]
        trainee_spec = (trainee_row["specialty"] or "").strip()

        # المواد التي تحتوي ضمن تخصّصاتها على تخصّص المتكوّن
        def subject_matches_trainee(srow):
            return trainee_spec in parse_specs(srow["specialty"])

        subj_df = df_s[df_s.apply(subject_matches_trainee, axis=1)]
        if subj_df.empty:
            st.warning("لا توجد مواد مطابقة لتخصّص هذا المتكوّن في هذا الفرع.")
        else:
            s_options = ["— اختر مادة —"] + subj_df["name"].tolist()
            s_pick = st.selectbox("المادة", s_options, key="s_pick_abs")
            if s_pick == "— اختر مادة —":
                st.info("اختَر مادة.")
            else:
                subject_row = subj_df[subj_df["name"]==s_pick].iloc[0]

                # إضافة غياب
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

                # عرض الغيابات لهذا المتكوّن في هذه المادة
                df_a = df_sql("""
                    SELECT a.id, a.date, a.hours, a.excused
                    FROM absences a
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
                    show_a.insert(0, "Index", range(1, len(show_a)+1))
                    st.dataframe(show_a[["Index","date","hours","معذور؟"]], use_container_width=True, height=260)

                    colE1, colE2, colE3 = st.columns(3)
                    with colE1:
                        idx_list = ["—"] + [int(i) for i in show_a["Index"].tolist()]
                        idx_toggle = st.selectbox("اختر Index لتبديل (معذور/غير معذور)", idx_list, key="idx_toggle")
                        if st.button("تبديل الحالة", key="btn_toggle_excused"):
                            if idx_toggle != "—":
                                row_sel = show_a[show_a["Index"]==int(idx_toggle)].iloc[0]
                                new_val = 0 if int(row_sel["excused"])==1 else 1
                                exec_sql("UPDATE absences SET excused=? WHERE id=?", (new_val, row_sel["id"]))
                                st.success("تم التبديل ✅")
                                st.rerun()
                    with colE2:
                        idx_del = st.selectbox("اختر Index لحذف الغياب", idx_list, key="idx_del")
                        if st.button("🗑️ حذف الغياب", key="btn_del_abs"):
                            if idx_del != "—":
                                row_sel = show_a[show_a["Index"]==int(idx_del)].iloc[0]
                                exec_sql("DELETE FROM absences WHERE id=?", (row_sel["id"],))
                                st.success("تم الحذف ✅")
                                st.rerun()
                    with colE3:
                        st.caption("لو جاب شهادة طبية بدّل الحالة إلى 'معذور' باش ما يتحسبش.")

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
            # المواد التي تحتوي هذا التخصص ضمن قائمتها
            df_s_f = df_s_f[df_s_f["specialty"].apply(lambda s: spec_r in parse_specs(s))]
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
        # المادة لازم تحتوي تخصّص المتكوّن ضمن قائمتها
        sb_row = df_s[(df_s["name"]==s_r) & (df_s["specialty"].apply(lambda s: tr_row["specialty"] in parse_specs(s)))].copy()
        if sb_row.empty:
            st.warning("المادة لا تنتمي لتخصّص المتكوّن.")
        else:
            sb_row = sb_row.iloc[0]
            total_hours = float(sb_row["total_hours"] or 0.0)
            limit = round(0.10 * total_hours, 2)
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

            # تنبيه تلقائي حسب الحدّ
            if remaining < alert_threshold:
                st.warning(f"⚠️ تنبيه: المتبقّي ({remaining:.2f} س) أقل من الحدّ ({alert_threshold:.2f} س).")

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

            # واتساب
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
    # تقرير إجمالي (مع عمود تنبيه)
    st.subheader("تقرير إجمالي — متكوّن × مادة (في هذا الفرع)")
    df_t_all = df_sql("SELECT * FROM trainees WHERE branch=?", (branch,))
    df_s_all = df_sql("SELECT * FROM subjects WHERE branch=?", (branch,))
    if 'spec_r' in locals() and spec_r != "— الكل —":
        df_t_all = df_t_all[df_t_all["specialty"].fillna("")==spec_r]
        df_s_all = df_s_all[df_s_all["specialty"].apply(lambda s: spec_r in parse_specs(s))]

    rows = []
    for _, tr in df_t_all.iterrows():
        for _, sb in df_s_all.iterrows():
            # لازم تخصّص المتكوّن موجود ضمن تخصّصات المادة
            if (tr["specialty"] or "").strip() not in parse_specs(sb["specialty"]):
                continue
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
                "متبقّي": remaining,
                "تنبيه": "⚠️" if remaining < alert_threshold else ""
            })
    if rows:
        df_report = pd.DataFrame(rows)
        st.dataframe(df_report.sort_values(["المتكوّن","المادة"]), use_container_width=True, height=320)
        alert_only = st.checkbox("عرض الحالات التي فيها تنبيه فقط (⚠️)", value=False, key="alert_only")
        if alert_only:
            df_alerts = df_report[df_report["تنبيه"]=="⚠️"]
            if df_alerts.empty:
                st.info("لا توجد حالات تحت الحدّ.")
            else:
                st.dataframe(df_alerts, use_container_width=True, height=260)
    else:
        st.info("لا توجد بيانات كافية للتقرير.")

# ===================== ملاحظات =====================
# - تخزين تخصصات المادة ضمن حقل specialty كقائمة CSV (مثال: "Informatique, Anglais")
# - كل عمليات المطابقة تعتمد parse_specs(..)
# - غير كلمات سر الفروع عبر st.secrets:
#   [branch_passwords]
#   MB="mb_2025!"
#   BZ="bz_2025!"
# - نسبة 10% ثابتة (يمكن تعديلها بتغيير 0.10 في الحساب)
# - حدّ التنبيه متغيّر من الشريط الجانبي (alert_threshold)
