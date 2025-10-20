# AttendanceHub.py
# نظام غيابات/حضور للمكوّنين والمتكوّنين — تخزين محلي (attendance_db.json) — واتساب تنبيهات
# مضاف: حقل "الاختصاص" للمتكوّن + فلترة حسب الاختصاص عند تسجيل الغياب
# مضاف: إدارة الغيابات (حذف/اعتبار بشهادة طبية/إلغاء الشهادة الطبية)

import os, json, uuid, urllib.parse
from datetime import datetime, date
from typing import Dict, Any, List

import streamlit as st
import pandas as pd

# ---------------- إعداد الصفحة ----------------
st.set_page_config(page_title="Attendance Hub", layout="wide")
st.markdown("""
<div style='text-align:center'>
  <h1>📝 Attendance Hub — إدارة الغيابات والحضور</h1>
  <p>متكوّنون 👥 | مواد 📚 | خطط ساعات ⏱️ | غيابات 🚫 | تنبيهات واتساب 💬</p>
</div>
<hr/>
""", unsafe_allow_html=True)

# ---------------- ثوابت/فروع ----------------
BRANCHES = ["Menzel Bourguiba", "Bizerte"]
ABSENCE_THRESHOLD_PCT = 0.10  # 10%

# ---------------- التخزين المحلي ----------------
ROOT_DIR = os.getcwd()
DB_PATH  = os.path.join(ROOT_DIR, "attendance_db.json")

def ensure_store():
    if not os.path.exists(DB_PATH):
        init = {
            "trainees": [],   # {id,name,phone,branch,specialty}
            "subjects": [],   # {id,name,branch}
            "plans": [],      # {id,trainee_id,subject_id,total_hours,weekly_hours,branch}
            "sessions": []    # {id,trainee_id,subject_id,date,hours_absent,reason,has_medical,branch}
        }
        save_db(init)

def load_db() -> Dict[str, Any]:
    ensure_store()
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db: Dict[str, Any]):
    tmp = DB_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DB_PATH)

# ---------------- أسرار اختيارية ----------------
def branch_password(branch: str) -> str:
    try:
        m = st.secrets["branch_passwords"]
        if "Menzel" in branch or branch == "MB": return str(m.get("MB",""))
        if "Bizerte" in branch or branch == "BZ": return str(m.get("BZ",""))
    except Exception:
        pass
    return ""

def whatsapp_number(branch: str) -> str:
    try:
        m = st.secrets["branch_whatsapp"]
        if "Menzel" in branch or branch=="MB": return str(m.get("MB",""))
        if "Bizerte" in branch or branch=="BZ": return str(m.get("BZ",""))
    except Exception:
        pass
    return ""

def wa_link(number: str, message: str) -> str:
    num = "".join(c for c in str(number) if c.isdigit())
    return f"https://wa.me/{num}?text={urllib.parse.quote(message)}" if num else ""

def norm_phone(s: str) -> str:
    """حوّل الهاتف إلى 216XXXXXXXX إن كان 8 أرقام محلية، وخلّي أي رقم ثاني كما هو بعد تنظيفه من غير الأرقام."""
    d = "".join(c for c in str(s) if c.isdigit())
    if d.startswith("216"):
        return d
    if len(d) == 8:
        return "216" + d
    return d

# ---------------- اختيار الفرع + قفل الموظفين ----------------
st.sidebar.subheader("⚙️ إعدادات")
CUR_BRANCH = st.sidebar.selectbox("اختر الفرع", BRANCHES, index=0)

need_pw = branch_password(CUR_BRANCH)
key_pw  = f"branch_pw_ok::{CUR_BRANCH}"
if need_pw:
    if key_pw not in st.session_state:
        st.session_state[key_pw] = False
    if not st.session_state[key_pw]:
        pw_try = st.sidebar.text_input("🔐 كلمة سرّ الفرع (للموظفين)", type="password")
        if st.sidebar.button("فتح"):
            if pw_try == need_pw:
                st.session_state[key_pw] = True
                st.sidebar.success("✅ تم الفتح")
            else:
                st.sidebar.error("❌ كلمة سر غير صحيحة")
        st.stop()

# ---------------- تحميل قاعدة البيانات ----------------
ensure_store()
db = load_db()
for k in ("trainees","subjects","plans","sessions"):
    db.setdefault(k, [])

# ---------------- تبويبات ----------------
tab_tr, tab_sub, tab_plan, tab_abs, tab_rep = st.tabs([
    "👥 المتكوّنون",
    "📚 المواد",
    "⏱️ الخطط",
    "🚫 الغيابات",
    "📊 التقارير & 💬 واتساب",
])

# =========================================================
# 👥 المتكوّنون
# =========================================================
with tab_tr:
    st.subheader(f"المتكوّنون — {CUR_BRANCH}")
    with st.form("add_trainee"):
        c1, c2, c3, c4 = st.columns(4)
        name      = c1.text_input("الاسم واللقب")
        phone     = c2.text_input("الهاتف")
        specialty = c3.text_input("الاختصاص")
        _         = c4.text_input("الفرع", value=CUR_BRANCH, disabled=True)
        sub = st.form_submit_button("➕ إضافة")
    if sub:
        if not name.strip() or not phone.strip():
            st.error("يرجى إدخال الاسم والهاتف.")
        else:
            db["trainees"].append({
                "id": uuid.uuid4().hex[:10],
                "name": name.strip(),
                "phone": norm_phone(phone),
                "branch": CUR_BRANCH,
                "specialty": specialty.strip()
            })
            save_db(db)
            st.success("✅ تمت الإضافة.")

    # قائمة
    tr_list = [t for t in db["trainees"] if t.get("branch")==CUR_BRANCH]
    if not tr_list:
        st.info("لا يوجد متكوّنون بعد.")
    else:
        tdf = pd.DataFrame(tr_list)
        tdf["الهاتف"]     = tdf["phone"].apply(lambda x: f"+{x}" if str(x).isdigit() else x)
        tdf["الاسم"]      = tdf["name"]
        tdf["الاختصاص"]   = tdf.get("specialty", "")
        st.dataframe(tdf[["الاسم","الهاتف","الاختصاص"]], use_container_width=True, height=360)

        # 🔴 حذف متكوّن كامل (مع خططه وجلساته)
        del_key = st.selectbox("اختر متكوّن للحذف (اختياري)", ["—"] + [f"{t['name']} (+{t['phone']})" for t in tr_list])
        if del_key != "—" and st.button("🗑️ حذف المتكوّن"):
            pid = next((t["id"] for t in tr_list if f"{t['name']} (+{t['phone']})"==del_key), None)
            if pid:
                db["trainees"]  = [x for x in db["trainees"] if x["id"] != pid]
                db["plans"]     = [x for x in db["plans"] if x["trainee_id"] != pid]
                db["sessions"]  = [x for x in db["sessions"] if x["trainee_id"] != pid]
                save_db(db)
                st.success("تم الحذف.")

# =========================================================
# 📚 المواد
# =========================================================
with tab_sub:
    st.subheader(f"المواد — {CUR_BRANCH}")
    with st.form("add_subject"):
        c1, c2 = st.columns(2)
        sub_name = c1.text_input("اسم المادة")
        _        = c2.text_input("الفرع", value=CUR_BRANCH, disabled=True)
        subm = st.form_submit_button("➕ إضافة")
    if subm:
        if not sub_name.strip():
            st.error("أدخل اسم المادة.")
        else:
            db["subjects"].append({
                "id": uuid.uuid4().hex[:10],
                "name": sub_name.strip(),
                "branch": CUR_BRANCH
            })
            save_db(db)
            st.success("✅ تمت الإضافة.")

    subs = [s for s in db["subjects"] if s.get("branch")==CUR_BRANCH]
    if not subs:
        st.info("لا توجد مواد بعد.")
    else:
        sdf = pd.DataFrame(subs)
        sdf["المادة"] = sdf["name"]
        st.dataframe(sdf[["المادة"]], use_container_width=True, height=320)

        del_s_key = st.selectbox("اختر مادة للحذف (اختياري)", ["—"]+[s["name"] for s in subs])
        if del_s_key != "—" and st.button("🗑️ حذف المادة"):
            sid = next((s["id"] for s in subs if s["name"]==del_s_key), None)
            if sid:
                db["subjects"] = [x for x in db["subjects"] if x["id"] != sid]
                db["plans"]    = [x for x in db["plans"] if x["subject_id"] != sid]
                db["sessions"] = [x for x in db["sessions"] if x["subject_id"] != sid]
                save_db(db)
                st.success("تم الحذف.")

# =========================================================
# ⏱️ الخطط (إجمالي/أسبوعي لكل متكوّن/مادة)
# =========================================================
with tab_plan:
    st.subheader(f"الخطط — {CUR_BRANCH}")
    tr_list = [t for t in db.get("trainees", []) if t.get("branch")==CUR_BRANCH]
    sub_list = [s for s in db.get("subjects", []) if s.get("branch")==CUR_BRANCH]

    if not tr_list or not sub_list:
        st.info("أضِف على الأقل متكوّنًا ومادة في الفرع الحالي.")
    else:
        # فلتر اختياري بالاختصاص
        specialties = sorted({(t.get("specialty") or "").strip() for t in tr_list if (t.get("specialty") or "").strip()})
        spec_pick = st.selectbox("فلترة حسب الاختصاص (اختياري)", ["الكل"] + specialties) if specialties else "الكل"
        tr_list_view = tr_list if spec_pick=="الكل" else [t for t in tr_list if (t.get("specialty") or "").strip()==spec_pick]

        if not tr_list_view:
            st.warning("لا توجد أسماء ضمن هذا الاختصاص.")
        else:
            tr_opts = {f"{t['name']} — +{t['phone']} — [{t.get('specialty','') or '-'}]": t for t in tr_list_view}
            tr_key  = st.selectbox("اختر المتكوّن", list(tr_opts.keys()))
            tr      = tr_opts[tr_key]

            sub_opts = {s["name"]: s for s in sub_list}
            sub_key  = st.selectbox("اختر المادة", list(sub_opts.keys()))
            subj     = sub_opts[sub_key]

            plans_list = db.get("plans", [])
            plan_exist = next(
                (p for p in plans_list
                 if p.get("trainee_id")==tr.get("id")
                 and p.get("subject_id")==subj.get("id")
                 and p.get("branch")==CUR_BRANCH),
                None
            )

            total_hours  = st.number_input(
                "إجمالي ساعات المادة للمتكوّن",
                min_value=0.0, step=1.0,
                value=float(plan_exist.get("total_hours", 0.0)) if plan_exist else 0.0
            )
            weekly_hours = st.number_input(
                "ساعات الأسبوع (افتراضي للحصص)",
                min_value=0.0, step=0.5,
                value=float(plan_exist.get("weekly_hours", 2.0)) if plan_exist else 2.0
            )

            c1, c2 = st.columns(2)
            if c1.button("💾 حفظ/تحديث الخطة"):
                if total_hours <= 0:
                    st.error("❌ إجمالي الساعات لازم > 0.")
                else:
                    if plan_exist:
                        plan_exist["total_hours"]  = float(total_hours)
                        plan_exist["weekly_hours"] = float(weekly_hours)
                    else:
                        db.setdefault("plans", []).append({
                            "id": uuid.uuid4().hex[:10],
                            "trainee_id": tr.get("id"),
                            "subject_id": subj.get("id"),
                            "total_hours": float(total_hours),
                            "weekly_hours": float(weekly_hours),
                            "branch": CUR_BRANCH
                        })
                    save_db(db)
                    st.success("✅ تم الحفظ.")

            if plan_exist and c2.button("🗑️ حذف الخطة"):
                db["plans"] = [p for p in db.get("plans", []) if p.get("id") != plan_exist.get("id")]
                save_db(db)
                st.success("تم الحذف.")

            # عرض جميع الخطط
            plans = [p for p in db.get("plans", []) if p.get("branch")==CUR_BRANCH]
            if plans:
                sp_map = {s["id"]: s["name"] for s in sub_list}
                tr_map = {t["id"]: f"{t['name']} (+{t['phone']})" for t in tr_list}
                t_spec = {t["id"]: (t.get("specialty") or "") for t in tr_list}
                pdf = pd.DataFrame(plans)
                pdf["المتكوّن"] = pdf["trainee_id"].map(tr_map)
                pdf["الاختصاص"] = pdf["trainee_id"].map(t_spec)
                pdf["المادة"]   = pdf["subject_id"].map(sp_map)
                pdf["إجمالي"]   = pdf["total_hours"]
                pdf["أسبوعي"]   = pdf["weekly_hours"]
                st.markdown("#### الخطط الحالية")
                st.dataframe(pdf[["المتكوّن","الاختصاص","المادة","إجمالي","أسبوعي"]], use_container_width=True)

# =========================================================
# 🚫 الغيابات
# =========================================================
with tab_abs:
    st.subheader(f"تسجيل الغيابات — {CUR_BRANCH}")
    tr_branch = [t for t in db.get("trainees", []) if t.get("branch")==CUR_BRANCH]
    sub_list  = [s for s in db.get("subjects", []) if s.get("branch")==CUR_BRANCH]

    if not tr_branch or not sub_list:
        st.info("لازم على الأقل متكوّن ومادة.")
    else:
        # ⬅️ فلترة إلزامية بالاختصاص قبل اختيار المتكوّن
        specialties = sorted({(t.get("specialty") or "").strip() for t in tr_branch if (t.get("specialty") or "").strip()})
        if not specialties:
            st.info("📌 لم تُسجَّل اختصاصات بعد. يمكنك إضافتها عند إضافة المتكوّن.")
            spec_pick = "الكل"
            tr_list_view = tr_branch
        else:
            spec_pick = st.selectbox("اختيار الاختصاص", specialties)
            tr_list_view = [t for t in tr_branch if (t.get("specialty") or "").strip()==spec_pick]

        if not tr_list_view:
            st.warning("لا توجد أسماء ضمن هذا الاختصاص في هذا الفرع.")
        else:
            tr_opts = {f"{t['name']} — +{t['phone']} — [{t.get('specialty','') or '-'}]": t for t in tr_list_view}
            tr_key  = st.selectbox("المتكوّن", list(tr_opts.keys()))
            tr      = tr_opts[tr_key]

            sub_opts = {s["name"]: s for s in sub_list}
            sub_key  = st.selectbox("المادة", list(sub_opts.keys()))
            subj     = sub_opts[sub_key]

            ses_date  = st.date_input("تاريخ الجلسة", value=date.today())
            abs_hours = st.number_input("ساعات الغياب", min_value=0.0, step=0.5, value=2.0)
            reason    = st.text_input("السبب (اختياري)")
            has_med   = st.checkbox("شهادة طبية؟ (يُستثنى من نسبة الغياب)")

            if st.button("➕ تسجيل الغياب"):
                if abs_hours <= 0:
                    st.error("الساعات لازم > 0.")
                else:
                    db["sessions"].append({
                        "id": uuid.uuid4().hex[:10],
                        "trainee_id": tr["id"],
                        "subject_id": subj["id"],
                        "date": ses_date.isoformat(),
                        "hours_absent": float(abs_hours),
                        "reason": reason.strip(),
                        "has_medical": bool(has_med),
                        "branch": CUR_BRANCH
                    })
                    save_db(db)
                    st.success("✅ تم التسجيل.")

    # عرض سجلات الغياب في الفرع مع فلترة
    sessions = [s for s in db.get("sessions", []) if s.get("branch")==CUR_BRANCH]
    if sessions:
        sp_map = {s["id"]: s["name"] for s in db.get("subjects", []) if s.get("branch")==CUR_BRANCH}
        tr_map = {t["id"]: f"{t['name']} (+{t['phone']})" for t in db.get("trainees", []) if t.get("branch")==CUR_BRANCH}
        tr_spec= {t["id"]: (t.get("specialty") or "") for t in db.get("trainees", []) if t.get("branch")==CUR_BRANCH}
        sdf = pd.DataFrame(sessions)
        sdf["المتكوّن"]   = sdf["trainee_id"].map(tr_map)
        sdf["الاختصاص"]   = sdf["trainee_id"].map(tr_spec)
        sdf["المادة"]     = sdf["subject_id"].map(sp_map)
        sdf["التاريخ"]    = pd.to_datetime(sdf["date"]).dt.strftime("%Y-%m-%d")
        sdf["ساعات الغياب"] = sdf["hours_absent"]
        sdf["شهادة طبية"]   = sdf["has_medical"].map({True:"نعم", False:"لا"})
        sdf["السبب"]        = sdf["reason"]
        st.markdown("#### سجلات الغياب (الفرع)")
        st.dataframe(sdf[["التاريخ","المتكوّن","الاختصاص","المادة","ساعات الغياب","شهادة طبية","السبب"]],
                     use_container_width=True, height=360)

        # ===== إدارة الغيابات (حذف / اعتبار بشهادة طبية / إلغاء الشهادة) =====
        st.markdown("---")
        st.markdown("### 🛠️ إدارة الغيابات")

        # اختيار متكوّن (بنفس فلترة الاختصاص)
        tr_admin_opts = {f"{t['name']} — +{t['phone']} — [{t.get('specialty','') or '-'}]": t for t in tr_branch}
        if tr_admin_opts:
            pick_tr_admin = st.selectbox("اختر المتكوّن لإدارة غياباته", list(tr_admin_opts.keys()))
            tr_admin = tr_admin_opts[pick_tr_admin]
            # جلسات المتكوّن المختار
            tr_sess = [s for s in sessions if s["trainee_id"]==tr_admin["id"]]
            if not tr_sess:
                st.info("لا توجد غيابات لهذا المتكوّن.")
            else:
                s_df = pd.DataFrame(tr_sess)
                s_df["عرض"] = s_df.apply(lambda r: f"{pd.to_datetime(r['date']).date()} — {sp_map.get(r['subject_id'],'-')} — {r['hours_absent']}h — {'طبي' if r.get('has_medical') else 'بدون طبي'}", axis=1)
                # Multi-select حسب ID
                select_ids = st.multiselect("اختر غيابات للتصرف فيها", options=list(s_df["id"]), format_func=lambda x: s_df.loc[s_df["id"]==x, "عرض"].iloc[0])

                c1, c2, c3 = st.columns(3)
                if c1.button("🗑️ حذف الغيابات المحدّدة", disabled=(len(select_ids)==0)):
                    before = len(db["sessions"])
                    db["sessions"] = [s for s in db["sessions"] if s["id"] not in select_ids]
                    save_db(db)
                    st.success(f"تم الحذف: {before - len(db['sessions'])} سجل.")

                if c2.button("✅ اعتبار المحدّدة بشهادة طبية", disabled=(len(select_ids)==0)):
                    cnt = 0
                    for s in db["sessions"]:
                        if s["id"] in select_ids:
                            if not s.get("has_medical"):
                                s["has_medical"] = True
                                cnt += 1
                    save_db(db)
                    st.success(f"تم وضع شهادة طبية لعدد {cnt}.")

                if c3.button("↩️ إلغاء الشهادة الطبية للمحدّدة", disabled=(len(select_ids)==0)):
                    cnt = 0
                    for s in db["sessions"]:
                        if s["id"] in select_ids:
                            if s.get("has_medical"):
                                s["has_medical"] = False
                                cnt += 1
                    save_db(db)
                    st.success(f"تم إلغاء الشهادة الطبية لعدد {cnt}.")

# =========================================================
# 📊 التقارير & 💬 واتساب
# =========================================================
with tab_rep:
    st.subheader(f"التقارير — {CUR_BRANCH}")

    tr_by_id = {t["id"]: t for t in db.get("trainees", []) if t.get("branch")==CUR_BRANCH}
    sub_by_id= {s["id"]: s for s in db.get("subjects", []) if s.get("branch")==CUR_BRANCH}
    plans    = [p for p in db.get("plans", []) if p.get("branch")==CUR_BRANCH]
    sess     = [s for s in db.get("sessions", []) if s.get("branch")==CUR_BRANCH]

    rows = []
    for p in plans:
        tid = p["trainee_id"]; sid = p["subject_id"]
        trainee = tr_by_id.get(tid); subj = sub_by_id.get(sid)
        if not trainee or not subj:
            continue

        total_hours  = float(p.get("total_hours", 0.0))
        weekly_hours = float(p.get("weekly_hours", 0.0))

        s_list = [s for s in sess if s["trainee_id"]==tid and s["subject_id"]==sid]
        absent_effective = sum(float(s["hours_absent"]) for s in s_list if not s.get("has_medical"))
        absent_medical   = sum(float(s["hours_absent"]) for s in s_list if s.get("has_medical"))

        pct = (absent_effective/total_hours)*100 if total_hours>0 else 0.0
        limit_hours = ABSENCE_THRESHOLD_PCT * total_hours
        remaining_to_limit = max(limit_hours - absent_effective, 0.0)

        rows.append({
            "trainee_id": tid,
            "subject_id": sid,
            "المتكوّن": f"{trainee['name']} (+{trainee['phone']})",
            "الاختصاص": trainee.get("specialty",""),
            "المادة": subj["name"],
            "إجمالي الساعات": total_hours,
            "ساعات أسبوعية": weekly_hours,
            "غياب فعلي (بدون طبّي)": round(absent_effective,2),
            "غياب بشهادة": round(absent_medical,2),
            "نسبة الغياب %": round(pct,2),
            "الحد (10%) ساعة": round(limit_hours,2),
            "متبقّي للحد": round(remaining_to_limit,2),
            "هاتف": trainee["phone"]
        })

    if not rows:
        st.info("لا توجد خطط بعد لإظهار التقرير.")
    else:
        rdf = pd.DataFrame(rows)
        # فلاتر
        c1, c2, c3 = st.columns(3)
        f_tr = c1.text_input("بحث بالمتكوّن/الهاتف")
        f_sb = c2.text_input("بحث بالمادة")
        spec_list = sorted({(r or "").strip() for r in rdf["الاختصاص"].fillna("") if (r or "").strip()})
        f_sp = c3.selectbox("فلترة بالاختصاص", ["الكل"] + spec_list) if spec_list else c3.selectbox("فلترة بالاختصاص", ["الكل"])

        view = rdf.copy()
        if f_tr.strip():
            q = f_tr.lower()
            view = view[view["المتكوّن"].str.lower().str.contains(q)]
        if f_sb.strip():
            q = f_sb.lower()
            view = view[view["المادة"].str.lower().str.contains(q)]
        if f_sp != "الكل":
            view = view[view["الاختصاص"]==f_sp]

        st.dataframe(
            view[["المتكوّن","الاختصاص","المادة","إجمالي الساعات","ساعات أسبوعية","غياب فعلي (بدون طبّي)","غياب بشهادة","نسبة الغياب %","الحد (10%) ساعة","متبقّي للحد"]],
            use_container_width=True, height=420
        )

        st.markdown("#### 💬 رسائل واتساب")
        if not view.empty:
            pick = st.selectbox("اختر سجل لإرسال رسالة", [f"{r['المتكوّن']} — {r['المادة']}" for _, r in view.iterrows()])
            if pick:
                row = view.iloc[[i for i, s in enumerate([f"{r['المتكوّن']} — {r['المادة']}" for _, r in view.iterrows()]) if s==pick][0]]
                name_phone = row["المتكوّن"]
                phone      = row["هاتف"]
                msg = (
                    f"Bonjour {name_phone.split('(+')[0].strip()},\n\n"
                    f"Rappel d'assiduité — Spécialité: {row['الاختصاص'] or '-'} — Matière: {row['المادة']}.\n"
                    f"Heures d'absence (hors certificats): {row['غياب فعلي (بدون طبّي)']} h\n"
                    f"Seuil de 10%: {row['الحد (10%) ساعة']} h\n"
                    f"Reste avant d'atteindre le seuil: {row['متبقّي للحد']} h\n\n"
                    f"Merci de respecter le planning. 😊"
                )
                link = wa_link(phone, msg)
                if link:
                    st.markdown(f"[📲 فتح واتساب للمرسل إليه]({link})")
                else:
                    st.warning("لم يتم تحديد رقم هاتف صالح.")

        # روابط جماعية للفرع
        st.markdown("##### روابط جماعية (كل الخطط في هذا الفرع)")
        bulk = []
        for _, r in rdf.iterrows():
            msg = (
                f"Bonjour {r['المتكوّن'].split('(+')[0].strip()},\n"
                f"Spécialité: {r['الاختصاص'] or '-'} — Matière: {r['المادة']}\n"
                f"Absences (hors certificats): {r['غياب فعلي (بدون طبّي)']} h\n"
                f"Seuil 10%: {r['الحد (10%) ساعة']} h — Reste: {r['متبقّي للحد']} h\n"
                f"Merci."
            )
            bulk.append((r["هاتف"], wa_link(r["هاتف"], msg)))
        if bulk:
            for phone, link in bulk[:200]:
                st.markdown(f"- {phone}: " + (f"[فتح واتساب]({link})" if link else "—"))
        else:
            st.caption("لا توجد عناصر لإظهار الروابط.")

st.caption("📦 يتم حفظ البيانات محليًا في attendance_db.json داخل مجلد التطبيق.")
