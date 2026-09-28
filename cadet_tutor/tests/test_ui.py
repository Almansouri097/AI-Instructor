"""Phase 12: right-to-left rendering of Arabic text."""
from src.ui import _paragraphs, is_rtl, rtl_html


def test_arabic_paragraph_is_rtl_and_right_aligned():
    out = rtl_html("**العاصبة** توضع فوق الجرح\n- لا توضع على المفصل")
    assert out.startswith('<div dir="rtl" style="text-align: right;')
    assert "<b>العاصبة</b>" in out and "• لا توضع" in out


def test_arabic_text_is_escaped():
    assert "&lt;script&gt;" in rtl_html("نص <script>")


def test_mixed_answer_splits_by_direction_and_keeps_paragraphs():
    text = ("Le garrot se place au-dessus de la plaie [guide, p.1].\n\n"
            "Deuxième paragraphe.\n"
            "« توضع العاصبة على بعد خمسة إلى سبعة سنتيمترات فوق الجرح »\n"
            "Il ne se place jamais sur une articulation.")
    blocks = _paragraphs(text)
    assert [is_rtl(b) for b in blocks] == [False, True, False]
    assert "\n\nDeuxième" in blocks[0]  # blank line kept: separate Markdown paragraphs


def test_french_with_short_arabic_quote_stays_ltr():
    assert not is_rtl("Le terme « العاصبة » désigne le garrot utilisé en cas d'hémorragie.")
