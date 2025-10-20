# AttendanceHub.py
# إدارة غيابات المتكونين — بدون Google Sheets
# حفظ محلّي في مجلّد att_data/ + توليد رسائل واتساب آليًا

import os, json, uuid, urllib.parse
from datetime import datetime, date
from typing import Dict, Any, List

import streamlit as st
import pandas as pd

# ================= إعداد الصفحة =================
st.set_page_config(page_title="Attendance Hub", layout="wide")
st.markdown("""
<div style='text-align:center'>
  <h1>🗂️ إدارة غيابات المتكوّنين</h1>
  <p>إضافة متكوّنين ومواد | تعليم الغيابات حسب الحصص | حساب تلقائي | رسالة واتساب</p>
</div>
<hr/>
""", unsafe_allow_html=True)

# ================= التخزين المحلي =================
ROOT = os.getcwd()
DATA_DIR = os.path.join(ROOT, "att_data")
IDX_PATH = os.path.join(DATA_DIR, "index.json")

def ensure_store():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(IDX_PATH):
        with open(IDX_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "trainees": [],   # [{id,name,phone}]
                "subjects": [],   # [{id,name,total_sessions}]
                "sessions": [],   # [{id,dt,subject_id,note}]
                "absences": [],   # [{session_id, trainee_id}]
                "settings": {     # صيغة الحساب
                    "formula_mode": "percentage",  # "percentage" أو "fixed"
                    "percentage_allowed": 20,      # % من إجمالي حصص المادة
                    "fixed_allowed": 3,            # حد أقصى ثابت
                    "wa_number_MB": "",            # رقم واتساب فرع منزل بورقيبة (اختياري)
                    "wa_number_BZ": "",            # رقم واتساب فرع بنزرت (اختياري)
                    "wa_branch_default": "Menzel Bourguiba"
                }
            }, f, ensure_ascii=False, indent=2)

def load_data() -> Dict[str, Any]:
    ensure_store()
    with open(IDX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: Dict[str, Any]):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = IDX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, IDX_PATH)

def human_dt(ts: str|date) -> str:
    if isinstance(ts, date):
        return ts.strftime("%Y-%m-%d")
    try:
        return datetime.fromisoformat(str(ts)).strftime("%Y-%m-%d")
    except Exception:
        return str(ts)

def wa_link(number: str, message: str) -> str:
    num = "".join(c for c in str(number) if c.isdigit())
    return f"https://wa.me/{num}?text={urllib.parse.quote(message)}" if num else ""

# ================= تبويبات الواجهة =================
tab_cfg, tab_lists, tab_mark, tab_dash, tab_wa = st.tabs([
    "⚙️ الإعدادات", "👥 القوائم", "📝 تعليم الغيابات", "📊 لوحة الإحصائيات", "💬 رسائل واتساب"
])

data = load_data()

# ---------------------------------------------------
# ⚙️ الإعدادات
# ---------------------------------------------------
with tab_cfg:
    st.subheader("صيغة حساب المسموح من الغيابات")
    c1, c2, c3 = st.columns(3)
    with c1:
        formula_mode = st.selectbox(
            "طريقة الحساب", ["percentage", "fixed"],
            index=0 if data["settings"].get("formula_mode","percentage")=="percentage" else 1
        )
    with c2:
        perc = st.number_input(
            "النسبة المسموح بها (%)",
            min_value=0, max_value=100, step=1,
            value=int(data["settings"].get("percentage_allowed", 20))
        )
    with c3:
        fixed = st.number_input(
            "حد ثابت للغيابات المسموح بها",
            min_value=0, max_value=100, step=1,
            value=int(data["settings"].get("fixed_allowed", 3))
        )

    st.markdown("---")
    st.subheader("أرقام واتساب للجهات (اختياري)")
    b1, b2, b3 = st.columns(3)
    with b1:
        wa_MB = st.text_input("رقم واتساب — منزل بورقيبة (مثال: 2169XXXXXXXX)",
                              value=data["settings"].get("wa_number_MB",""))
    with b2:
        wa_BZ = st.text_input("رقم واتساب — بنزرت (مثال: 2169XXXXXXXX)",
                              value=data["settings"].get("wa_number_BZ",""))
    with b3:
        default_branch = st.selectbox("الفرع الافتراضي للإرسال", ["Menzel Bourguiba","Bizerte"],
                                      index=(0 if data["settings"].get("wa_branch_default","Menzel Bourguiba")=="Menzel Bourguiba" else 1))

    if st.button("💾 حفظ الإعدادات"):
        data["settings"]["formula_mode"] = formula_mode
        data["settings"]["percentage_allowed"] = int(perc)
        data["settings"]["fixed_allowed"] = int(fixed)
        data["settings"]["wa_number_MB"] = wa_MB.strip()
        data["settings"]["wa_number_BZ"] = wa_BZ.strip()
        data["settings"]["wa_branch_default"] = default_branch
        save_data(data)
        st.success("تمّ الحفظ ✅")

# ---------------------------------------------------
# 👥 القوائم (متكوّنين + مواد + حصص)
# ---------------------------------------------------
with tab_lists:
    st.subheader("المتكوّنون (تُضاف يدويًا)")
    c1, c2, c3 = st.columns(3)
    with c1:
        tr_name = st.text_input("اسم المتكوّن")
    with c2:
        tr_phone = st.text_input("هاتف المتكوّن (واتساب)")
    with c3:
        if st.button("➕ إضافة متكوّن"):
            if tr_name.strip():
                data = load_data()
                data["trainees"].append({
                    "id": uuid.uuid4().hex[:10],
                    "name": tr_name.strip(),
                    "phone": "".join(ch for ch in tr_phone if ch.isdigit())
                })
                save_data(data)
                st.success("تمت الإضافة ✅")
            else:
                st.error("يرجى إدخال الاسم.")

    if data["trainees"]:
        df_t = pd.DataFrame(data["trainees"])
        df_t_display = df_t.rename(columns={"name":"الاسم","phone":"الهاتف","id":"الكود"})
        st.dataframe(df_t_display[["الاسم","الهاتف","الكود"]], use_container_width=True, height=260)
    else:
        st.info("لا يوجد متكوّنون بعد.")

    st.markdown("---")
    st.subheader("المواد (Matières)")
    s1, s2, s3 = st.columns(3)
    with s1:
        subj_name = st.text_input("اسم المادة/الوحدة")
    with s2:
        total_sessions = st.number_input("إجمالي الحصص المخطّطة", min_value=1, step=1, value=12)
    with s3:
        if st.button("➕ إضافة مادة"):
            if subj_name.strip():
                data = load_data()
                data["subjects"].append({
                    "id": uuid.uuid4().hex[:10],
                    "name": subj_name.strip(),
                    "total_sessions": int(total_sessions)
                })
                save_data(data)
                st.success("تمت الإضافة ✅")
            else:
                st.error("يرجى إدخال اسم المادة.")

    if data["subjects"]:
        df_s = pd.DataFrame(data["subjects"])
        df_s_display = df_s.rename(columns={"name":"المادة","total_sessions":"إجمالي الحصص","id":"الكود"})
        st.dataframe(df_s_display[["المادة","إجمالي الحصص","الكود"]], use_container_width=True, height=260)
    else:
        st.info("لا توجد مواد بعد.")

    st.markdown("---")
    st.subheader("إدارة الحصص (Sessions)")
    if not data["subjects"]:
        st.warning("أضف مواد أولًا.")
    else:
        ss1, ss2, ss3 = st.columns(3)
        with ss1:
            sess_date = st.date_input("تاريخ الحصة", value=date.today())
        with ss2:
            subj_idx_map = {s["name"]: s["id"] for s in data["subjects"]}
            subj_pick = st.selectbox("المادة", list(subj_idx_map.keys()))
        with ss3:
            sess_note = st.text_input("ملاحظة (اختياري)")

        if st.button("➕ إنشاء حصة"):
            data = load_data()
            data["sessions"].append({
                "id": uuid.uuid4().hex[:10],
                "dt": str(sess_date),
                "subject_id": subj_idx_map[subj_pick],
                "note": sess_note.strip()
            })
            save_data(data)
            st.success("تم إنشاء الحصة ✅")

        if data["sessions"]:
            # عرض آخر 30 جلسة
            df_sessions = pd.DataFrame(data["sessions"])
            # وصل اسم المادة
            subj_map = {s["id"]: s["name"] for s in data["subjects"]}
            df_sessions["المادة"] = df_sessions["subject_id"].map(subj_map)
            df_sessions["التاريخ"] = pd.to_datetime(df_sessions["dt"]).dt.strftime("%Y-%m-%d")
            df_sessions["الملاحظة"] = df_sessions["note"]
            df_sessions["الكود"] = df_sessions["id"]
            st.dataframe(df_sessions[["التاريخ","المادة","الملاحظة","الكود"]].sort_values("التاريخ", ascending=False).head(30),
                         use_container_width=True, height=300)
        else:
            st.info("لا توجد حصص بعد.")

# ---------------------------------------------------
# 📝 تعليم الغيابات
# ---------------------------------------------------
with tab_mark:
    st.subheader("علّم الغيابات على حصة")
    if not data["sessions"]:
        st.warning("لا توجد حصص. أنشئ حصة من تبويب القوائم.")
    elif not data["trainees"]:
        st.warning("لا يوجد متكوّنون. أضف متكوّنين من تبويب القوائم.")
    else:
        # اختيار حصة
        subj_map = {s["id"]: s["name"] for s in data["subjects"]}
        # اسم عرضي للجلسة
        def _label(sess):
            return f"{human_dt(sess['dt'])} — {subj_map.get(sess['subject_id'],'?')} — [{sess['id']}]"

        sess_options = {_label(s): s["id"] for s in sorted(data["sessions"], key=lambda x: x["dt"], reverse=True)}
        sess_pick_label = st.selectbox("اختر الحصة", list(sess_options.keys()))
        sess_id = sess_options[sess_pick_label]

        # المتغيبون
        tr_map = {t["name"]: t["id"] for t in data["trainees"]}
        # من غاب مسبقًا؟
        prev_abs = {a["trainee_id"] for a in data["absences"] if a["session_id"] == sess_id}
        absent_names_default = [t["name"] for t in data["trainees"] if t["id"] in prev_abs]

        abs_sel = st.multiselect("اختر المتغيبين", list(tr_map.keys()), default=absent_names_default)

        # حفظ
        if st.button("💾 حفظ الغيابات"):
            data = load_data()
            # احذف السجلات القديمة لهذه الحصة
            data["absences"] = [a for a in data["absences"] if a["session_id"] != sess_id]
            # أضف الجديدة
            for n in abs_sel:
                data["absences"].append({
                    "session_id": sess_id,
                    "trainee_id": tr_map[n]
                })
            save_data(data)
            st.success("تمّ الحفظ ✅")

        # عرض سريع: من تغيب؟
        if prev_abs or abs_sel:
            cur = set(tr_map[n] for n in abs_sel)
            df_prev = pd.DataFrame([t for t in data["trainees"] if t["id"] in cur])
            if not df_prev.empty:
                st.markdown("#### قائمة المتغيبين المختارة لهذه الحصة")
                st.dataframe(df_prev.rename(columns={"name":"الاسم","phone":"الهاتف"})[["الاسم","الهاتف"]], use_container_width=True)

# ---------------------------------------------------
# 📊 لوحة الإحصائيات
# ---------------------------------------------------
with tab_dash:
    st.subheader("الإحصائيات حسب المادة والمتكوّن")
    if not data["subjects"] or not data["trainees"]:
        st.info("أضف مواد ومتكوّنين أولًا.")
    else:
        # اختيار مادة (اختياري)
        subj_all_map = {s["name"]: s["id"] for s in data["subjects"]}
        subj_choice = st.selectbox("فلتر حسب المادة (اختياري)", ["— الكل —"] + list(subj_all_map.keys()))
        subj_filter = None if subj_choice == "— الكل —" else subj_all_map[subj_choice]

        # حساب الغيابات
        df_abs = pd.DataFrame(data["absences"])
        df_sessions = pd.DataFrame(data["sessions"])
        df_tr = pd.DataFrame(data["trainees"])
        df_subj = pd.DataFrame(data["subjects"])

        if df_sessions.empty:
            st.info("لا توجد حصص بعد.")
        else:
            # ربط الأسماء
            if not df_abs.empty:
                df_abs = df_abs.merge(df_sessions[["id","subject_id"]].rename(columns={"id":"session_id"}),
                                      on="session_id", how="left")

            rows = []
            for t in data["trainees"]:
                for s in data["subjects"]:
                    if subj_filter and s["id"] != subj_filter:
                        continue
                    total_sess = int(s.get("total_sessions", 0))
                    # عدد الغيابات لهذا المتكوّن في هذه المادة
                    if df_abs.empty:
                        abs_count = 0
                    else:
                        mask = (df_abs["trainee_id"]==t["id"]) & (df_abs["subject_id"]==s["id"])
                        abs_count = int(mask.sum())

                    # allowed per settings
                    mode = data["settings"].get("formula_mode","percentage")
                    if mode == "percentage":
                        p = int(data["settings"].get("percentage_allowed", 20))
                        allowed = int((total_sess * p + 99) // 100)  # ceil( total * p% / 100 )
                    else:
                        allowed = int(data["settings"].get("fixed_allowed", 3))
                    allowed = max(0, allowed)

                    remaining = max(allowed - abs_count, 0)
                    rows.append({
                        "المتكوّن": t["name"],
                        "الهاتف": t["phone"],
                        "المادة": s["name"],
                        "إجمالي الحصص": total_sess,
                        "المسموح بالغياب": allowed,
                        "عدد الغيابات": abs_count,
                        "المتبقي": remaining,
                        "حالة": ("⚠️ تجاوز" if abs_count > allowed else ("⏳ اقترب" if abs_count == allowed else "✅ ضمن الحد"))
                    })

            df_out = pd.DataFrame(rows)
            if df_out.empty:
                st.info("لا توجد بيانات لعرضها.")
            else:
                # ترتيب
                df_out = df_out.sort_values(["المادة","المتكوّن"]).reset_index(drop=True)
                st.dataframe(df_out, use_container_width=True, height=450)

                # إجمالي سريع لكل مادة
                st.markdown("#### ملخّص المادة (عدد الغيابات الإجمالي)")
                grp = df_out.groupby("المادة", dropna=False)["عدد الغيابات"].sum().reset_index()
                grp = grp.sort_values("عدد الغيابات", ascending=False)
                st.dataframe(grp, use_container_width=True)

# ---------------------------------------------------
# 💬 رسائل واتساب
# ---------------------------------------------------
with tab_wa:
    st.subheader("توليد رسالة واتساب لكل متكوّن")
    if not data["subjects"] or not data["trainees"]:
        st.info("أضف مواد ومتكوّنين أولًا.")
    else:
        # اختيار الفرع (لتحديد رقم الإرسال إن حبّيت)
        branch = st.selectbox("اختيار الفرع المرسل", ["Menzel Bourguiba","Bizerte"],
                              index=(0 if data["settings"].get("wa_branch_default","Menzel Bourguiba")=="Menzel Bourguiba" else 1))
        wa_num = data["settings"].get("wa_number_MB","") if branch=="Menzel Bourguiba" else data["settings"].get("wa_number_BZ","")

        # اختيار المتكوّن والمادة
        tr_map_by_name = {t["name"]: t for t in data["trainees"]}
        tr_pick_name = st.selectbox("اختر المتكوّن", list(tr_map_by_name.keys()))
        subj_map_name = {s["name"]: s for s in data["subjects"]}
        subj_pick_name = st.selectbox("اختر المادة", list(subj_map_name.keys()))

        t = tr_map_by_name[tr_pick_name]
        s = subj_map_name[subj_pick_name]

        # احسب بياناته لهذه المادة
        df_abs = pd.DataFrame(data["absences"])
        df_sess = pd.DataFrame(data["sessions"])
        if df_abs.empty or df_sess.empty:
            abs_count = 0
        else:
            df_abs = df_abs.merge(df_sess[["id","subject_id"]].rename(columns={"id":"session_id"}),
                                  on="session_id", how="left")
            mask = (df_abs["trainee_id"]==t["id"]) & (df_abs["subject_id"]==s["id"])
            abs_count = int(mask.sum())

        total_sess = int(s.get("total_sessions", 0))
        mode = data["settings"].get("formula_mode","percentage")
        if mode == "percentage":
            p = int(data["settings"].get("percentage_allowed", 20))
            allowed = int((total_sess * p + 99)//100)
        else:
            allowed = int(data["settings"].get("fixed_allowed", 3))
        allowed = max(0, allowed)
        remaining = max(allowed - abs_count, 0)

        default_msg = (
            f"السلام عليكم {t['name']}،\n"
            f"بخصوص مادة: {s['name']}\n"
            f"عدد الغيابات: {abs_count}\n"
            f"المسموح بالغياب: {allowed}\n"
            f"المتبقي قبل تجاوز الحد: {remaining}\n"
            f"الرجاء الالتزام بالحضور. شكراً لتفهمكم."
        )
        msg = st.text_area("نص رسالة واتساب (يمكنك تعديله قبل الإرسال):", value=default_msg, height=140)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**إرسال للمتكوّن مباشرة**")
            link_student = wa_link(t["phone"], msg)
            if link_student:
                st.markdown(f"[📲 فتح واتساب للمتكوّن]({link_student})")
            else:
                st.caption("الهاتف غير مضبوط للمتكوّن.")

        with c2:
            st.markdown("**إشعار للفرع (اختياري)**")
            link_branch = wa_link(wa_num, f"تنبيه فرع {branch}:\n{msg}")
            if wa_num and link_branch:
                st.markdown(f"[📣 إرسال للفرع]({link_branch})")
            else:
                st.caption("رقم واتساب الفرع غير مضبوط.")

        with c3:
            st.markdown("**ملخص سريع**")
            st.metric("غيابات", abs_count)
            st.metric("المسموح", allowed)
            st.metric("المتبقي", remaining)
