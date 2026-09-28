"""Streamlit helpers for mixed French / Arabic / English text."""
import html
import re

import streamlit as st

from src.extract import arabic_share

# Inputs pick their direction from what is typed (Arabic flows right to left).
BIDI_CSS = """<style>
textarea, input, [data-testid="stChatInputTextArea"], [data-testid="stRadio"] label,
[data-testid="stMarkdownContainer"] li { unicode-bidi: plaintext; text-align: start; }
</style>"""


def is_rtl(text: str) -> bool:
    """True if a paragraph is mostly Arabic."""
    return arabic_share(text) > 0.5


def _paragraphs(text: str) -> list[str]:
    """Split into blocks of consecutive lines with the same direction."""
    blocks: list[tuple[bool, list[str]]] = []  # (rtl, lines); blank lines stay in their block
    for line in text.splitlines():
        if not line.strip():
            if blocks:
                blocks[-1][1].append(line)
        elif blocks and is_rtl(line) == blocks[-1][0]:
            blocks[-1][1].append(line)
        else:
            blocks.append((is_rtl(line), [line]))
    return ["\n".join(lines).strip() for _, lines in blocks]


def rtl_html(text: str, style: str = "") -> str:
    """An Arabic paragraph as right-to-left HTML, keeping bold and bullet points."""
    lines = []
    for line in html.escape(text).splitlines():
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"^\s*[-*]\s+", "• ", line)
        lines.append(line)
    return f'<div dir="rtl" style="text-align: right; {style}">{"<br>".join(lines)}</div>'


def show_text(text: str, small: bool = False) -> None:
    """Render text; Arabic paragraphs right to left, others as normal Markdown."""
    for para in _paragraphs(text):
        if is_rtl(para):
            style = "font-size: 0.85em; opacity: 0.75;" if small else ""
            st.markdown(rtl_html(para, style), unsafe_allow_html=True)
        elif small:
            st.caption(para)
        else:
            st.markdown(para)


def show_info(text: str) -> None:
    """Like st.info, right to left when the text is Arabic."""
    if is_rtl(text):
        box = "background: rgba(28,131,225,0.1); padding: 0.75em 1em; border-radius: 0.5em;"
        st.markdown(rtl_html(text, box), unsafe_allow_html=True)
    else:
        st.info(text)
