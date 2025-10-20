# AbsencesHub_Branches.py
# منظومة غيابات تربط إجمالي الساعات وساعات الأسبوع "بالمادة" لكل متكوّن
# مع فروع (MB / Bizerte) — كل فرع عندو متكوّنين/مواد/خطط/حصص خاصين بيه
# تخزين محلّي (بدون Google Sheets): attn/index.json

import os, json, uuid, urllib.parse
from datetime import datetime, date
from typing import Dict, Any, List

import streamlit as st
import pandas as pd

# ---------------- إعداد عام ----------------
st.set_page_config(page_title="منظومة الغيابات (حسب المادة/الفرع)", layout="wide")
st.markdown("""
<div style='text-align:center'>
  <h1>🕒 منظومة الغيابات — حسب المادة ولكل فرع</h1>
  <p>إدارة متكوّنين ومواد وخطط (Total/Weekly) لكل مادة، تسجيل حصص، حساب 10%</p>
</div>
<hr/>
""", unsafe_allow_html=True)

# ---------------- تخزين محلّي ----------------
ROOT = os.getcwd()
DATA_DIR = os.path.join(ROOT, "attn")
IDX_PATH = os.path.join(DATA_DIR, "index.json")

def ensure_store():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(IDX_PATH):
        with open(IDX_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "trainees": [],   # {id,name,phone,branch,created_at}
                "subjects": [],   # {id,name,branch,created_at}
                "plans": [],      # {id, trainee_id, subject_id, total_hours, weekly_hours, branch}
                "sessions": []    # {id, trainee_id, subject_id, date, hours, is_absent, medical, note, branch, ts}
            }, f, ensure_ascii=False, indent=2)

def load_db() -> Dict[str, Any]:
    ensure_store()
    try:
        with open(IDX_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"trainees": [], "subjects": [], "plans": [], "sessions": []}

def save_db(db: Dict[str, Any]):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = IDX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, IDX_PATH)

def normalize_tn_phone(s: str) -> str:
    digits = "".join(ch for ch in str(s) if ch.isdigit())
    if digits.startswith("216"): return digits
    if len(digits) == 8: return "216" + digits
    return digits

def wa_link(number: str, message: str) -> str:
    num = "".join(c for c in str(number) if c.isdigit())
    return f"https://wa.me/{num}?text={urllib.parse.quote(message)}" if num else ""

ABS_LIMIT_PCT = 10.0  # % الحد الأقصى للغياب

# ---------------- دخول حسب الفرع ----------------
def branch_password(branch: str) -> str:
    try:
        m = st.secrets["branch_passwords"]
        if branch == "Menzel Bourguiba" or branch == "MB": return str(m.get("MB",""))
        if branch == "Bizerte" or branch == "BZ": return str(m.get("BZ",""))
    except Exception:
        pass
    return ""

st.sidebar.subheader("اختيار الفرع")
branch_pick = st.sidebar.selectbox("الفرع", ["Menzel Bourguiba", "Bizerte"])
need_pw = branch_password(branch_pick)
key_gate = f"branch_ok::{branch_pick}"

if need_pw:
    if key_gate not in st.session_state: st.session_state[key_gate] = False
    if not st.session_state[key_gate]:
        pwd = st.sidebar.text_input("كلمة سر الفرع", type="password")
        if st.sidebar.button("دخول الفرع"):
            if pwd == need_pw:
                st.session_state[key_gate] = True
                st.sidebar.success("تم الفتح ✅")
            else:
                st.sidebar.error("كلمة سر غير صحيحة ❌")
        st.stop()

# بعد الفتح
db = load_db()

# helpers للفرع الحالي
def fbranch(x: str) -> str:
    return "MB" if "Menzel" in x else ("BZ" if "Bizerte" in x else x)

CUR_BRANCH = "MB" if "Menzel" in branch_pick else "BZ"

# ---------------- Tabs ----------------
tab_mng, tab_plan, tab_sess, tab_dash = st.tabs([
    "👥 إدارة المتكوّنين والمواد", "🧩 الخطط (Total/Weekly) لكل مادة", "🗓️ تسجيل الحصص/الغياب", "📊 ملخّص وحسابات"
])

# ========== 1) إدارة المتكوّنين والمواد ==========
with tab_mng:
    colA, colB = st.columns(2)

    with colA:
        st.subheader("➕ إضافة متكوّن (مربوط بالفرع)")
        with st.form("add_trainee"):
            tr_name = st.text_input("الاسم الكامل")
            tr_phone = st.text_input("الهاتف")
            subm_tr = st.form_submit_button("حفظ المتكوّن")
        if subm_tr:
            if not tr_name.strip() or not tr_phone.strip():
                st.error("❌ الاسم وال/or الهاتف مفقود.")
            else:
                new_rec = {
                    "id": uuid.uuid4().hex[:10],
                    "name": tr_name.strip(),
                    "phone": normalize_tn_phone(tr_phone),
                    "branch": CUR_BRANCH,
                    "created_at": datetime.now().isoformat(timespec="seconds")
                }
                db["trainees"].append(new_rec)
                save_db(db)
                st.success("✅ تمّت إضافة المتكوّن.")

        tr_list = [t for t in db["trainees"] if t.get("branch")==CUR_BRANCH]
        if tr_list:
            st.markdown("#### قائمة المتكوّنين (الفرع الحالي)")
            tdf = pd.DataFrame(tr_list)
            tdf["الهاتف"] = tdf["phone"]
            tdf["الاسم"] = tdf["name"]
            tdf["الفرع"] = tdf["branch"]
            tdf["أضيف في"] = pd.to_datetime(tdf["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(tdf[["الاسم","الهاتف","الفرع","أضيف في"]], use_container_width=True)

    with colB:
        st.subheader("📚 المواد (حسب الفرع)")
        with st.form("add_subject"):
            subj_name = st.text_input("اسم المادة")
            ok_s = st.form_submit_button("إضافة مادة")
        if ok_s:
            if not subj_name.strip():
                st.error("❌ اسم المادة مطلوب.")
            else:
                exists = any((s["name"].strip().lower()==subj_name.strip().lower() and s.get("branch")==CUR_BRANCH) for s in db["subjects"])
                if exists:
                    st.warning("⚠️ المادة موجودة في هذا الفرع.")
                else:
                    db["subjects"].append({
                        "id": uuid.uuid4().hex[:10],
                        "name": subj_name.strip(),
                        "branch": CUR_BRANCH,
                        "created_at": datetime.now().isoformat(timespec="seconds")
                    })
                    save_db(db)
                    st.success("✅ تمّت إضافة المادة.")

        sub_list = [s for s in db["subjects"] if s.get("branch")==CUR_BRANCH]
        if sub_list:
            sdf = pd.DataFrame(sub_list)
            sdf["المادة"] = sdf["name"]
            sdf["الفرع"]  = sdf["branch"]
            sdf["أضيفت في"] = pd.to_datetime(sdf["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(sdf[["المادة","الفرع","أضيفت في"]], use_container_width=True)

# ========== 2) الخطط (Total/Weekly) لكل مادة ==========
with tab_plan:
    st.subheader("ربط متكوّن بمادة مع (إجمالي ساعات + ساعات أسبوع)")
    tr_list = [t for t in db["trainees"] if t.get("branch")==CUR_BRANCH]
    sub_list = [s for s in db["subjects"] if s.get("branch")==CUR_BRANCH]

    if not tr_list or not sub_list:
        st.info("أضِف على الأقل متكوّنًا ومادة في الفرع الحالي.")
    else:
        tr_opts = {f"{t['name']} — +{t['phone']}": t for t in tr_list}
        tr_key  = st.selectbox("اختر المتكوّن", list(tr_opts.keys()))
        tr      = tr_opts[tr_key]

        sub_opts = {s["name"]: s for s in sub_list}
        sub_key  = st.selectbox("اختر المادة", list(sub_opts.keys()))
        subj     = sub_opts[sub_key]

        # إن كانت خطة موجودة، نملأها للعرض/التعديل
        plan_exist = next((p for p in db["plans"]
                           if p["trainee_id"]==tr["id"] and p["subject_id"]==subj["id"] and p.get("branch")==CUR_BRANCH), None)

        total_hours  = st.number_input("إجمالي ساعات المادة للمتكوّن", min_value=0.0, step=1.0,
                                       value=float(plan_exist["total_hours"]) if plan_exist else 0.0)
        weekly_hours = st.number_input("ساعات الأسبوع (Default للحصة)", min_value=0.0, step=0.5,
                                       value=float(plan_exist["weekly_hours"]) if plan_exist else 2.0)

        c1, c2 = st.columns(2)
        if c1.button("💾 حفظ/تحديث الخطة"):
            if total_hours <= 0:
                st.error("❌ إجمالي الساعات لازم > 0.")
            else:
                if plan_exist:
                    plan_exist["total_hours"] = float(total_hours)
                    plan_exist["weekly_hours"] = float(weekly_hours)
                else:
                    db["plans"].append({
                        "id": uuid.uuid4().hex[:10],
                        "trainee_id": tr["id"],
                        "subject_id": subj["id"],
                        "total_hours": float(total_hours),
                        "weekly_hours": float(weekly_hours),
                        "branch": CUR_BRANCH
                    })
                save_db(db)
                st.success("✅ تم الحفظ.")

        if plan_exist and c2.button("🗑️ حذف الخطة"):
            db["plans"] = [p for p in db["plans"] if p["id"] != plan_exist["id"]]
            save_db(db)
            st.success("تم الحذف.")

        # عرض كل الخطط في الفرع
        plans = [p for p in db["plans"] if p.get("branch")==CUR_BRANCH]
        if plans:
            sp_map = {s["id"]: s["name"] for s in sub_list}
            tr_map = {t["id"]: f"{t['name']} (+{t['phone']})" for t in tr_list}
            pdf = pd.DataFrame(plans)
            pdf["المتكوّن"] = pdf["trainee_id"].map(tr_map)
            pdf["المادة"]   = pdf["subject_id"].map(sp_map)
            pdf["إجمالي"]   = pdf["total_hours"]
            pdf["أسبوعي"]   = pdf["weekly_hours"]
            st.markdown("#### الخطط الحالية (الفرع)")
            st.dataframe(pdf[["المتكوّن","المادة","إجمالي","أسبوعي"]], use_container_width=True)

# ========== 3) تسجيل الحصص/الغياب ==========
with tab_sess:
    st.subheader("تسجيل حصة (حاضر/غائب) — الفرع الحالي")

    tr_list = [t for t in db["trainees"] if t.get("branch")==CUR_BRANCH]
    sub_list = [s for s in db["subjects"] if s.get("branch")==CUR_BRANCH]
    if not tr_list or not sub_list:
        st.info("أضِف متكوّنين ومواد في الفرع.")
    else:
        tr_opts = {f"{t['name']} — +{t['phone']}": t for t in tr_list}
        tr_key  = st.selectbox("اختر المتكوّن", list(tr_opts.keys()))
        tr      = tr_opts[tr_key]

        sub_opts = {s["name"]: s for s in sub_list}
        sub_key  = st.selectbox("اختر المادة", list(sub_opts.keys()))
        subj     = sub_opts[sub_key]

        # جلب خطة المادة لهذا المتكوّن
        plan = next((p for p in db["plans"]
                     if p["trainee_id"]==tr["id"] and p["subject_id"]==subj["id"] and p.get("branch")==CUR_BRANCH), None)
        if not plan:
            st.warning("لا توجد خطة (Total/Weekly) لهذا المتكوّن في هذه المادة. أنشئها في تبويب الخطط.")
        default_hours = float(plan["weekly_hours"]) if plan and float(plan["weekly_hours"])>0 else 2.0

        sess_date = st.date_input("تاريخ الحصة", value=date.today())
        sess_hours = st.number_input("ساعات الحصة", min_value=0.5, step=0.5, value=default_hours)
        is_absent  = st.checkbox("المتكوّن غائب؟")
        medical    = st.checkbox("غياب بشهادة طبية؟ (لا يُحتسب)", value=False) if is_absent else False
        note       = st.text_area("ملاحظة (اختياري)")

        if st.button("💾 حفظ الحصة"):
            rec = {
                "id": uuid.uuid4().hex[:10],
                "trainee_id": tr["id"],
                "subject_id": subj["id"],
                "date": sess_date.isoformat(),
                "hours": float(sess_hours),
                "is_absent": bool(is_absent),
                "medical": bool(medical),
                "note": note.strip(),
                "branch": CUR_BRANCH,
                "ts": datetime.now().isoformat(timespec="seconds")
            }
            db["sessions"].append(rec)
            save_db(db)
            st.success("✅ تمّ الحفظ.")

        # عرض حصص المتكوّن في المادة
        sess = [s for s in db["sessions"] if s.get("branch")==CUR_BRANCH and s["trainee_id"]==tr["id"] and s["subject_id"]==subj["id"]]
        if sess:
            df = pd.DataFrame(sess)
            df["التاريخ"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df["الساعات"] = df["hours"].astype(float)
            df["غائب؟"] = df["is_absent"].map({True:"نعم", False:"لا"})
            df["طبي؟"] = df["medical"].map({True:"نعم", False:"لا"})
            df = df.sort_values(["date","ts"])
            st.markdown("#### حصص هذا المتكوّن في هذه المادة")
            st.dataframe(df[["التاريخ","الساعات","غائب؟","طبي؟","note"]], use_container_width=True)

# ========== 4) ملخص وحسابات ==========
with tab_dash:
    st.subheader("حساب الغياب 10% — حسب المادة أو إجمالي المواد (الفرع الحالي)")

    tr_list = [t for t in db["trainees"] if t.get("branch")==CUR_BRANCH]
    if not tr_list:
        st.info("لا يوجد متكوّنون في هذا الفرع.")
    else:
        tr_opts = {f"{t['name']} — +{t['phone']}": t for t in tr_list}
        tr_key  = st.selectbox("اختر المتكوّن", list(tr_opts.keys()), key="dash_tr")
        tr      = tr_opts[tr_key]

        # اختيار مادة أو الكل
        sub_list = [s for s in db["subjects"] if s.get("branch")==CUR_BRANCH]
        sub_choices = ["(الكل)"] + [s["name"] for s in sub_list]
        sub_pick = st.selectbox("المادة", sub_choices)

        # خرائط
        sub_map_id2name = {s["id"]: s["name"] for s in sub_list}
        sub_map_name2id = {s["name"]: s["id"] for s in sub_list}

        # كل خطط هذا المتكوّن في الفرع
        plans = [p for p in db["plans"] if p.get("branch")==CUR_BRANCH and p["trainee_id"]==tr["id"]]

        # الحصص الكل
        sess_all = [s for s in db["sessions"] if s.get("branch")==CUR_BRANCH and s["trainee_id"]==tr["id"]]

        def compute_for_subject(subject_id: str):
            plan = next((p for p in plans if p["subject_id"]==subject_id), None)
            tot = float(plan["total_hours"]) if plan else 0.0
            sessions = [s for s in sess_all if s["subject_id"]==subject_id]
            sched = float(sum(s["hours"] for s in sessions))
            absent_eff = float(sum(s["hours"] for s in sessions if s["is_absent"] and not s["medical"]))
            pct = (absent_eff / tot * 100.0) if tot > 0 else 0.0
            remain = max(0.0, 0.10*tot - absent_eff)
            return tot, sched, absent_eff, pct, remain

        if sub_pick == "(الكل)":
            # تجميع عبر كل المواد
            totals = scheds = absents = 0.0
            for p in plans:
                t, s, a, _, _ = compute_for_subject(p["subject_id"])
                totals  += t
                scheds  += s
                absents += a
            pct_all = (absents / totals * 100.0) if totals > 0 else 0.0
            remain_all = max(0.0, 0.10*totals - absents)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("📚 إجمالي برنامج (كل المواد)", f"{totals:.1f} س")
            c2.metric("🗓️ مسجّل", f"{scheds:.1f} س")
            c3.metric("⛔ غياب فعلي", f"{absents:.1f} س")
            c4.metric("📊 % الغياب", f"{pct_all:.2f}%")
            c5.metric("🟢 الباقي قبل 10%", f"{remain_all:.1f} س")

            # تفصيل حسب المادة
            if plans:
                rows = []
                for p in plans:
                    t, s, a, pct, rem = compute_for_subject(p["subject_id"])
                    rows.append({
                        "المادة": sub_map_id2name.get(p["subject_id"], "?"),
                        "إجمالي": t,
                        "مجدول": s,
                        "غياب فعلي": a,
                        "%": round(pct,2),
                        "باقي قبل 10%": rem
                    })
                st.markdown("#### تفصيل حسب المادة")
                st.dataframe(pd.DataFrame(rows), use_container_width=True)

            msg = (
                f"سلام {tr['name']},\n"
                f"ملخص الغياب على كل المواد:\n"
                f"- غياب فعلي: {absents:.1f} س من إجمالي {totals:.1f} س ({pct_all:.2f}%).\n"
                f"- الباقي قبل 10%: {remain_all:.1f} س.\n"
                f"لو عندك شهادات طبية لبعض الغيابات، ابعثهالنا.\n"
                f"شكراً."
            )
            st.markdown(f"[📲 إرسال واتساب]({wa_link(tr['phone'], msg)})")

        else:
            sid = sub_map_name2id.get(sub_pick)
            t, s, a, pct, rem = compute_for_subject(sid)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("📚 إجمالي برنامج (المادة)", f"{t:.1f} س")
            c2.metric("🗓️ مسجّل", f"{s:.1f} س")
            c3.metric("⛔ غياب فعلي", f"{a:.1f} س")
            c4.metric("📊 % الغياب", f"{pct:.2f}%")
            c5.metric("🟢 الباقي قبل 10%", f"{rem:.1f} س")

            # جدول حصص المادة
            sess = [x for x in sess_all if x["subject_id"]==sid]
            if sess:
                df = pd.DataFrame(sess)
                df["التاريخ"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                df["الساعات"] = df["hours"]
                df["غائب؟"]   = df["is_absent"].map({True:"نعم", False:"لا"})
                df["طبي؟"]    = df["medical"].map({True:"نعم", False:"لا"})
                st.markdown("#### حصص المادة (للمتكوّن)")
                st.dataframe(df[["التاريخ","الساعات","غائب؟","طبي؟","note"]], use_container_width=True)

            msg = (
                f"سلام {tr['name']},\n"
                f"ملخص الغياب في مادة {sub_pick}:\n"
                f"- غياب فعلي: {a:.1f} س من إجمالي {t:.1f} س ({pct:.2f}%).\n"
                f"- الباقي قبل 10%: {rem:.1f} س.\n"
                f"لو عندك شهادة طبية لغياب سابق، ابعثهالنا.\n"
                f"شكراً."
            )
            st.markdown(f"[📲 إرسال واتساب]({wa_link(tr['phone'], msg)})")

    # إدارة سريعة للحذف
    st.markdown("---")
    st.subheader("🧹 حذف جلسة (اختياري)")
    # جميع الجلسات لهذا الفرع (اختيار متكوّن أولاً أسهل)
    tr_all_opts = {f"{t['name']} — +{t['phone']}": t for t in [t for t in db["trainees"] if t.get("branch")==CUR_BRANCH]}
    if tr_all_opts:
        pick_tr = st.selectbox("اختر متكوّن", list(tr_all_opts.keys()), key="cleanup_tr")
        tsel = tr_all_opts[pick_tr]
        sess_sel = [s for s in db["sessions"] if s.get("branch")==CUR_BRANCH and s["trainee_id"]==tsel["id"]]
        if sess_sel:
            sub_map = {s["id"]: s["name"] for s in [x for x in db["subjects"] if x.get("branch")==CUR_BRANCH]}
            items = [
                f"{i+1}. {x['date']} — {sub_map.get(x['subject_id'],'?')} — {x['hours']}س — {'غائب' if x['is_absent'] else 'حاضر'}{' (طبي)' if x['medical'] else ''}"
                for i,x in enumerate(sess_sel)
            ]
            choose = st.selectbox("اختر جلسة للحذف", ["(لا شيء)"] + items)
            if choose != "(لا شيء)":
                idx = items.index(choose)
                del_id = sess_sel[idx]["id"]
                if st.button("❗ حذف الجلسة المختارة"):
                    db["sessions"] = [s for s in db["sessions"] if s["id"] != del_id]
                    save_db(db)
                    st.success("تم الحذف.")
        else:
            st.caption("لا توجد جلسات لهذا المتكوّن في هذا الفرع.")
