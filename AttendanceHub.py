import streamlit as st
import random
import pandas as pd
from datetime import datetime, timedelta
from io import StringIO

# ==========================
# English Exam — 4 Épreuves
# Sections: Listening • Reading (Comprehension) • Use of English • Writing
# Levels: A1 / A2 / B1 / B2
# ==========================

st.set_page_config(page_title="English Exam — 4 Épreuves", layout="wide")

# ---------- Styles ----------
st.markdown(
    """
    <style>
      .title {text-align:center; font-size: 36px; font-weight:800; margin-bottom:0}
      .subtitle {text-align:center; color:#555; margin-top:4px}
      .card {background:#fff; padding:18px 20px; border-radius:16px; box-shadow:0 6px 24px rgba(0,0,0,0.06); margin-bottom:12px}
      .muted {color:#666}
      .kpi {font-size:28px; font-weight:700}
      .badge {display:inline-block; padding:4px 10px; border-radius:999px; background:#eef2ff; color:#3730a3; font-weight:700; font-size:12px}
      .ok {color:#16a34a; font-weight:700}
      .bad {color:#b91c1c; font-weight:700}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div class='title'>English Placement / Exam</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>4 Épreuves • Listening / Reading / Use of English / Writing</div>", unsafe_allow_html=True)

# ---------- Config ----------
LEVEL_ORDER = ["A1", "A2", "B1", "B2"]
SECTION_ORDER = ["Listening", "Reading", "Use of English", "Writing"]
LEVEL_TIME = {
    "A1": {"Listening": 8, "Reading": 8, "Use of English": 8, "Writing": 15},
    "A2": {"Listening": 10, "Reading": 10, "Use of English": 10, "Writing": 20},
    "B1": {"Listening": 12, "Reading": 12, "Use of English": 12, "Writing": 25},
    "B2": {"Listening": 15, "Reading": 15, "Use of English": 15, "Writing": 30},
}
PASS_MARK = 60
Q_PER = {"Listening": 6, "Reading": 6, "Use of English": 8}

# ---------- Question Banks ----------
# (مختصر هنا لتوفير المساحة، يحتوي نفس بنوك الأسئلة Listening / Reading / Use of English / Writing كما في النسخة السابقة)

# -------------- (ضع هنا كل البنوك من الكود السابق كما هي: L_BANK, R_PASSAGES, U_BANK, W_PROMPTS) --------------

# ---------- State ----------
def init_state():
    if "started" not in st.session_state:
        st.session_state.started = False
    for k, v in {"name": "", "level": "A1", "seed": random.randint(1, 10_000_000)}.items():
        st.session_state.setdefault(k, v)
    st.session_state.setdefault("answers", {s: {} for s in SECTION_ORDER})
    st.session_state.setdefault("deadline", None)

init_state()

# ---------- Helpers ----------
def pick_items(level, bank, n):
    """Return n items for a given level."""
    rnd = random.Random(st.session_state.seed)
    if isinstance(bank, dict):
        pool = list(bank.get(level, []))
    else:
        pool = list(bank)
    rnd.shuffle(pool)
    return pool[:n]

def reading_items(level, n):
    data = R_PASSAGES[level]
    qs = data["qs"][:]
    rnd = random.Random(st.session_state.seed)
    rnd.shuffle(qs)
    return data["text"], qs[:n]

def set_deadline(level):
    minutes = sum(LEVEL_TIME[level].values())
    st.session_state.deadline = datetime.utcnow() + timedelta(minutes=minutes)

def time_left_str():
    if not st.session_state.deadline:
        return ""
    left = st.session_state.deadline - datetime.utcnow()
    if left.total_seconds() <= 0:
        return "00:00"
    mm, ss = divmod(int(left.total_seconds()), 60)
    return f"{mm:02d}:{ss:02d}"

def score_mcq(items, user_map):
    correct = 0
    rows = []
    for i, it in enumerate(items):
        q = it.get("q") if isinstance(it, dict) else it[0]
        opts = it.get("options") if isinstance(it, dict) else it[1]
        ans = it.get("answer") if isinstance(it, dict) else it[2]
        user = user_map.get(i)
        ok = (user == ans)
        correct += int(ok)
        rows.append({"Q#": i + 1, "Question": q, "User": user or "", "Correct": ans, "IsCorrect": ok})
    pct = round(100 * correct / max(1, len(items)), 1)
    return pct, pd.DataFrame(rows)

def score_writing(text, level):
    min_w = {"A1": 50, "A2": 80, "B1": 120, "B2": 180}[level]
    max_w = {"A1": 70, "A2": 100, "B1": 150, "B2": 220}[level]
    kws = W_PROMPTS[level][1]
    wc = len(text.strip().split()) if text.strip() else 0
    hits = sum(1 for k in kws if k.lower() in text.lower())
    base = 40 if min_w <= wc <= max_w else 20 if wc > 0 else 0
    kw_score = min(60, hits * 12)
    pct = min(100, base + kw_score)
    return pct, wc, hits, kws

# ---------- Sidebar ----------
with st.sidebar:
    st.header("Setup")
    st.session_state.name = st.text_input("Candidate name", value=st.session_state.name)
    st.session_state.level = st.selectbox("Level", LEVEL_ORDER, index=LEVEL_ORDER.index(st.session_state.level))
    st.session_state.seed = st.number_input("Random seed", value=st.session_state.seed, step=1, format="%d")
    st.caption("⏱ Time per section set by level. Total time shows on top.")
    if not st.session_state.started:
        if st.button("▶️ Start Exam"):
            st.session_state.answers = {s: {} for s in SECTION_ORDER}
            st.session_state.started = True
            set_deadline(st.session_state.level)
    else:
        if st.button("🔁 Restart (new shuffle)"):
            st.session_state.seed = random.randint(1, 10_000_000)
            st.session_state.answers = {s: {} for s in SECTION_ORDER}
            set_deadline(st.session_state.level)

# ---------- Main ----------
if st.session_state.started:
    k1, k2, k3 = st.columns([1, 1, 2])
    with k1:
        st.markdown("**Level**")
        st.markdown(f"<span class='badge'>{st.session_state.level}</span>", unsafe_allow_html=True)
    with k2:
        st.markdown("**Time Left**")
        st.markdown(f"<div class='kpi'>{time_left_str()}</div>", unsafe_allow_html=True)
    with k3:
        st.info("Complete the four sections, then click Submit All at the bottom.")

    if time_left_str() == "00:00":
        st.warning("Time is up! Auto-submitting your exam.")

    lvl = st.session_state.level
    L_items = pick_items(lvl, L_BANK, Q_PER["Listening"])
    R_text, R_items = reading_items(lvl, Q_PER["Reading"])
    U_raw = pick_items(lvl, U_BANK, Q_PER["Use of English"])
    U_items = [{"q": q, "options": opts, "answer": ans} for (q, opts, ans) in U_raw]

    tabs = st.tabs(SECTION_ORDER)

    # Listening
    with tabs[0]:
        for i, it in enumerate(L_items):
            st.markdown(f"**L{i+1}.** {it['q']}")
            with st.expander("Transcript (if no audio)"):
                st.caption(it["transcript"])
            st.session_state.answers["Listening"][i] = st.radio("Select one:", it["options"], index=None, key=f"L_{i}")
            st.divider()

    # Reading
    with tabs[1]:
        st.info(R_text)
        for i, (q, opts, ans) in enumerate(R_items):
            st.markdown(f"**R{i+1}.** {q}")
            st.session_state.answers["Reading"][i] = st.radio("Select one:", opts, index=None, key=f"R_{i}")
            st.divider()

    # Use of English
    with tabs[2]:
        for i, it in enumerate(U_items):
            st.markdown(f"**U{i+1}.** {it['q']}")
            st.session_state.answers["Use of English"][i] = st.radio("Select one:", it["options"], index=None, key=f"U_{i}")
            st.divider()

    # Writing
    with tabs[3]:
        prompt, kws = W_PROMPTS[lvl]
        st.write(f"**Prompt:** {prompt}")
        st.caption(f"Try to include: {', '.join(kws)}")
        st.session_state.answers["Writing"][0] = st.text_area("Your essay:", height=220, key="W_0")

    # Submit
    if st.button("✅ Submit All", type="primary") or time_left_str() == "00:00":
        L_pct, L_df = score_mcq(L_items, st.session_state.answers["Listening"])
        R_df_items = [{"q": q, "options": opts, "answer": ans} for (q, opts, ans) in R_items]
        R_pct, R_df = score_mcq(R_df_items, st.session_state.answers["Reading"])
        U_pct, U_df = score_mcq(U_items, st.session_state.answers["Use of English"])
        W_text = st.session_state.answers["Writing"].get(0, "")
        W_pct, wc, hits, kws = score_writing(W_text, lvl)

        overall = round((L_pct + R_pct + U_pct + W_pct) / 4, 1)

        st.success(f"**Overall Score: {overall}%** — {'✅ PASS' if overall >= PASS_MARK else '❌ FAIL'}")
        st.write({"Listening": L_pct, "Reading": R_pct, "Use of English": U_pct, "Writing": W_pct})
        st.caption(f"Writing: {wc} words, {hits}/{len(kws)} keywords")

        def to_csv_bytes(df):
            buf = StringIO()
            df.to_csv(buf, index=False)
            return buf.getvalue().encode()

        st.download_button("⬇️ Listening report (CSV)", to_csv_bytes(L_df))
        st.download_button("⬇️ Reading report (CSV)", to_csv_bytes(R_df))
        st.download_button("⬇️ UseOfEnglish report (CSV)", to_csv_bytes(U_df))

        st.session_state.started = False
        st.session_state.deadline = None

else:
    st.info("اختار المستوى واضغط Start Exam باش تبدأ الـ4 إبراڤ (Listening / Reading / Use of English / Writing).")
