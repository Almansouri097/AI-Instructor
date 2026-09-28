"""Streamlit UI for the local cadet tutor.

Run from the project root:
    streamlit run app.py
"""
import streamlit as st

from src import config, llm
from src.ingest import get_collection
from src.modes import ask, order, quiz

st.set_page_config(page_title="Cadet Tutor", page_icon="🎖️", layout="wide")


def show_sources(hits) -> None:
    if not hits:
        return
    with st.expander(f"Sources ({len(hits)})"):
        for h in hits:
            st.markdown(f"**{h.label}** · {config.LEVEL_NAMES.get(h.level, '?')} · similarity {h.score:.2f}")
            st.caption(h.text[:600] + ("…" if len(h.text) > 600 else ""))


# --- sidebar: user and health ---------------------------------------------------
with st.sidebar:
    st.title("🎖️ Cadet Tutor")
    user = st.selectbox("Signed in as", list(config.USERS))
    level = config.USERS[user]
    st.caption(f"Clearance: **{config.LEVEL_NAMES[level]}** (level {level})")
    if st.session_state.get("user") != user:  # clear state when switching user
        st.session_state.clear()
        st.session_state.user = user

    problems = llm.check_ollama()
    if problems:
        for p in problems:
            st.error(p)
        st.stop()
    chunks = get_collection().count()
    if chunks == 0:
        st.warning("The document store is empty. Run `python -m src.ingest` first.")
        st.stop()
    st.caption(f"{chunks} chunks indexed · model `{config.LLM_MODEL}` · fully local")

tab_ask, tab_quiz, tab_order = st.tabs(["Ask", "Quiz", "Order review"])

# --- Ask ----------------------------------------------------------------------------
with tab_ask:
    history = st.session_state.setdefault("history", [])
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if question := st.chat_input("Ask about doctrine, law of armed conflict, SOPs…"):
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"), st.spinner("Searching documents…"):
            try:
                res = ask.answer(question, level, history)
            except llm.OllamaError as exc:
                st.error(str(exc))
                st.stop()
            st.markdown(res.text)
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
                st.markdown(f"{icon} **{i + 1}.** Correct answer: *{q.options[q.answer]}*  \n{q.explanation} {q.source}")

# --- Order review ----------------------------------------------------------------------
with tab_order:
    st.caption("Paste your five-paragraph order. It is graded against the rubric in data/order_rubric.json.")
    text = st.text_area("Your order", height=320, key="order_text")
    if st.button("Assess order", disabled=not text.strip()):
        with st.spinner("Assessing…"):
            try:
                result = order.assess(text, level)
            except llm.OllamaError as exc:
                st.error(str(exc))
                st.stop()
        st.metric("Total", f"{result.total}/{result.max_total}")
        for c in result.criteria:
            st.progress(c.score / c.max, text=f"{c.title}: {c.score}/{c.max}")
            st.caption(c.feedback)
        if result.overall:
            st.info(result.overall)
        show_sources(result.sources)
