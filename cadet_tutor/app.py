"""Streamlit UI for the local cadet tutor.

Run from the project root:
    streamlit run app.py
"""
import streamlit as st

from src import audit, config, demo, llm
from src.ui import BIDI_CSS, show_info, show_text
from src.ingest import get_collection
from src.modes import ask, order, quiz

st.set_page_config(page_title="Cadet Tutor", page_icon="🎖️", layout="wide")
st.markdown(BIDI_CSS, unsafe_allow_html=True)


def reset_state(keep: tuple[str, ...] = ()) -> None:
    """Forget conversations, quizzes and orders; keep only the listed keys."""
    for key in list(st.session_state):
        if key not in keep:
            del st.session_state[key]


def show_sources(hits) -> None:
    if not hits:
        return
    with st.expander(f"Sources ({len(hits)})"):
        for h in hits:
            st.markdown(f"**{h.label}** · {config.LEVEL_NAMES.get(h.level, '?')} · {h.lang} · similarity {h.score:.2f}")
            show_text(h.text[:600] + ("…" if len(h.text) > 600 else ""), small=True)


# --- sidebar: user and health ---------------------------------------------------
with st.sidebar:
    st.title("🎖️ Cadet Tutor")
    user = st.selectbox("Signed in as", list(config.USERS), key="user_select")
    level = config.USERS[user]
    st.caption(f"Clearance: **{config.LEVEL_NAMES[level]}** (level {level})")
    if st.session_state.get("user") != user:  # clear state when switching user
        reset_state(keep=("user_select", "demo_log"))
        st.session_state.user = user

    problems = llm.check_ollama()
    if problems:
        for p in problems:
            st.error(p)
        st.stop()

    if st.button("Demo", use_container_width=True, help="Load the sample documents and reset the app"):
        with st.spinner("Loading demo documents…"):
            try:
                log = demo.load()
            except demo.DemoError as exc:
                st.error(str(exc))
                st.stop()
        reset_state()  # back to a clean Cadet session
        st.session_state.demo_log = log
        st.rerun()
    if log := st.session_state.get("demo_log"):
        st.success("Demo loaded.")
        with st.expander("Ingestion log"):
            st.code(log)

    chunks = get_collection().count()
    if chunks == 0:
        st.warning("The document store is empty. Click **Demo** or run `python -m src.ingest`.")
        st.stop()
    st.caption(f"{chunks} chunks indexed · model `{config.LLM_MODEL}` · fully local")

AUDIT_LEVEL = config.USERS["Instructor"]
names = ["Ask", "Quiz", "Order review"] + (["Audit"] if level >= AUDIT_LEVEL else [])
tab_ask, tab_quiz, tab_order, *tab_audit = st.tabs(names)

# --- Ask ----------------------------------------------------------------------------
with tab_ask:
    history = st.session_state.setdefault("history", [])
    for msg in history:
        with st.chat_message(msg["role"]):
            show_text(msg["content"])
    if question := st.chat_input("Ask about doctrine, law of armed conflict, SOPs…"):
        with st.chat_message("user"):
            show_text(question)
        with st.chat_message("assistant"), st.spinner("Searching documents…"):
            try:
                with audit.context(user, level, "ask"):
                    res = ask.answer(question, level, history)
            except llm.OllamaError as exc:
                st.error(str(exc))
                st.stop()
            show_text(res.text)
            for w in res.warnings:
                st.warning(w)
            show_sources(res.sources)
        history += [{"role": "user", "content": question}, {"role": "assistant", "content": res.text}]

# --- Quiz ---------------------------------------------------------------------------
with tab_quiz:
    c1, c2, c3 = st.columns([3, 1, 1])
    topic = c1.text_input("Topic", placeholder="e.g. treatment of prisoners of war")
    n = c2.number_input("Questions", 1, 10, 5)
    if c3.button("Generate", use_container_width=True):
        with st.spinner("Writing questions…"):
            try:
                with audit.context(user, level, "quiz"):
                    st.session_state.quiz = quiz.generate(topic, level, int(n))
            except llm.OllamaError as exc:
                st.error(str(exc))
        st.session_state.pop("quiz_done", None)

    qs = st.session_state.get("quiz")
    if qs == []:
        st.info("No questions could be generated from your cleared documents. Try another topic.")
    elif qs:
        with st.form("quiz_form"):
            picks = []
            for i, q in enumerate(qs):
                choice = st.radio(f"**{i + 1}. {q.question}**", q.options, index=None, key=f"q{i}")
                picks.append(q.options.index(choice) if choice is not None else None)
            if st.form_submit_button("Submit answers"):
                st.session_state.quiz_done = picks
        if (picks := st.session_state.get("quiz_done")) is not None:
            st.subheader(f"Score: {quiz.score(qs, picks)}/{len(qs)}")
            for i, (q, p) in enumerate(zip(qs, picks)):
                icon = "✅" if p == q.answer else "❌"
                st.markdown(f"{icon} **{i + 1}.** {q.source}")
                show_text(f"**{q.options[q.answer]}**\n{q.explanation}")

# --- Order review ----------------------------------------------------------------------
with tab_order:
    st.caption("Paste your five-paragraph order. It is graded against the rubric in data/order_rubric.json.")

    def _load_sample() -> None:
        if name := st.session_state.get("sample_order"):
            st.session_state.order_text = demo.sample_order(name)

    st.selectbox(
        "Or load a sample order", list(demo.SAMPLE_ORDERS), index=None,
        key="sample_order", on_change=_load_sample, placeholder="Choose a sample…",
    )
    text = st.text_area("Your order", height=320, key="order_text")
    if st.button("Assess order", disabled=not text.strip()):
        with st.spinner("Assessing…"):
            try:
                with audit.context(user, level, "order"):
                    result = order.assess(text, level)
            except llm.OllamaError as exc:
                st.error(str(exc))
                st.stop()
        st.metric("Total", f"{result.total}/{result.max_total}")
        for c in result.criteria:
            st.progress(c.score / c.max, text=f"{c.title}: {c.score}/{c.max}")
            show_text(c.feedback, small=True)
        if result.overall:
            show_info(result.overall)
        show_sources(result.sources)

# --- Audit (Instructors only: the tab is not created for other users) --------------
if tab_audit:
    with tab_audit[0]:
        st.caption(f"Every query, from the local audit log `{config.AUDIT_DB.name}` (latest first).")
        entries = audit.rows()
        c1, c2, c3 = st.columns(3)
        who = c1.multiselect("User", sorted({r["user"] for r in entries}))
        modes = c2.multiselect("Mode", sorted({r["mode"] for r in entries}))
        flagged_only = c3.checkbox("Only flagged queries")
        shown = [r for r in entries
                 if (not who or r["user"] in who) and (not modes or r["mode"] in modes)
                 and (not flagged_only or r["flags"])]
        st.metric("Queries", len(shown))
        st.dataframe(
            [{"time (UTC)": r["ts"], "user": r["user"], "level": r["level"], "mode": r["mode"],
              "flags": "; ".join(r["flags"]), "query": r["query"], "documents": ", ".join(r["docs"])}
             for r in shown],
            use_container_width=True, hide_index=True,
        )
