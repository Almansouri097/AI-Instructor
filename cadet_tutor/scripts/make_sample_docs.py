"""Generate small fictional training PDFs in data/docs for trying the tutor.

Usage (from the project root):
    python -m scripts.make_sample_docs

Writes plain PDFs with no extra dependencies. Replace them with your real
documents and update data/levels.csv accordingly.
"""
import textwrap
from pathlib import Path

from src import config

DOCS: dict[str, list[str]] = {
    "geneva_conventions_extracts.pdf": [
        "GENEVA CONVENTIONS - TRAINING EXTRACTS (UNCLASSIFIED)\n\n"
        "This handout summarises selected provisions of the Geneva Conventions of 1949 for "
        "cadet instruction. It is a study aid, not a substitute for the full treaty text.\n\n"
        "Common Article 3. Persons taking no active part in hostilities, including members of "
        "armed forces who have laid down their arms and those placed hors de combat by sickness, "
        "wounds or detention, shall in all circumstances be treated humanely, without adverse "
        "distinction. Violence to life and person, cruel treatment and torture, the taking of "
        "hostages and outrages upon personal dignity are prohibited at any time and in any place.",
        "First Convention, Article 12. Members of the armed forces who are wounded or sick shall "
        "be respected and protected in all circumstances. They shall be treated humanely and cared "
        "for by the Party in whose power they may be. Only urgent medical reasons authorise "
        "priority in the order of treatment.\n\n"
        "Third Convention, Article 13. Prisoners of war must at all times be humanely treated and "
        "protected, particularly against acts of violence or intimidation and against insults and "
        "public curiosity. Measures of reprisal against prisoners of war are prohibited.\n\n"
        "Third Convention, Article 17. Every prisoner of war, when questioned, is bound to give "
        "only his surname, first names and rank, date of birth, and army, regimental, personal or "
        "serial number. No physical or mental torture, nor any other form of coercion, may be "
        "inflicted on prisoners of war to secure information of any kind.",
    ],
    "five_paragraph_order_guide.pdf": [
        "THE FIVE-PARAGRAPH ORDER - CADET GUIDE (UNCLASSIFIED)\n\n"
        "An operation order (OPORD) is issued in five paragraphs, always in the same sequence: "
        "1. Situation, 2. Mission, 3. Execution, 4. Service Support (Sustainment), "
        "5. Command and Signal. The fixed sequence lets subordinates find information quickly "
        "under pressure.\n\n"
        "Paragraph 1 - Situation. Describe enemy forces (composition, disposition, strength and "
        "most likely course of action), friendly forces (the mission of the higher unit and of "
        "adjacent units), attachments and detachments, and the effects of terrain and weather.",
        "Paragraph 2 - Mission. The mission is a single sentence that answers the five Ws: who, "
        "what, when, where and why. It uses a doctrinal task verb (for example seize, clear, "
        "block, secure) and ends with a purpose introduced by 'in order to'.\n\n"
        "Paragraph 3 - Execution. Begin with the commander's intent: purpose, key tasks and end "
        "state. Then give the concept of operations (scheme of manoeuvre and fires), tasks to each "
        "subordinate element, and coordinating instructions such as timings, control measures and "
        "rules of engagement.",
        "Paragraph 4 - Service Support. Cover supply (rations, water, ammunition), transport, "
        "the medical plan including casualty collection points and evacuation, and the handling "
        "of prisoners and detainees.\n\n"
        "Paragraph 5 - Command and Signal. State where the commander will be, the succession of "
        "command, radio frequencies and call signs, passwords or challenge-and-reply, and the "
        "signals for key events such as lifting fire.\n\n"
        "Common cadet errors: a mission with no purpose, an execution paragraph with no "
        "commander's intent, and no succession of command.",
    ],
    "platoon_sop_restricted.pdf": [
        "PLATOON STANDING OPERATING PROCEDURES (RESTRICTED - TRAINING EXAMPLE)\n\n"
        "Section 4 - Patrol preparation. Before any patrol each rifleman carries a minimum of "
        "six filled magazines, two litres of water and one day of rations. The section "
        "commander confirms holdings at the pre-patrol inspection, 30 minutes before the "
        "line of departure.\n\n"
        "Section 5 - Night procedures. Sentries use the challenge-and-reply procedure: the sentry "
        "halts the approaching person at a safe distance, calls the challenge word once in a low "
        "voice, and waits for the reply word. If the reply is wrong or not given, the sentry "
        "detains the person and alerts the section commander. Challenge and reply words change "
        "daily at 1800.",
    ],
    "exercise_iron_cedar_opord.pdf": [
        "EXERCISE IRON CEDAR - OPERATION ORDER 01 (CONFIDENTIAL - FICTIONAL EXERCISE)\n\n"
        "Situation. A notional enemy reconnaissance platoon occupies the farm complex at grid "
        "GR 4521 7834 and is expected to withdraw north when engaged.\n\n"
        "Mission. 2nd Platoon clears the farm complex at GR 4521 7834 by 0700 on D+1 in order "
        "to secure the company's northern flank.\n\n"
        "Execution. H-hour is 0530 on D+1. 1 Section provides fire support from the tree line; "
        "2 and 3 Sections assault from the west. The exercise directing staff are the only "
        "persons authorised to release this order to participants.",
    ],
}

# --- minimal PDF writer ------------------------------------------------------

_W, _H, _MARGIN, _FONT, _LEAD = 612, 792, 60, 11, 15


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _page_stream(text: str) -> bytes:
    lines: list[str] = []
    for para in text.split("\n"):
        lines.extend(textwrap.wrap(para, 90) or [""])
    ops = [f"BT /F1 {_FONT} Tf {_LEAD} TL {_MARGIN} {_H - _MARGIN} Td"]
    ops += [f"({_escape(line)}) Tj T*" for line in lines]
    ops.append("ET")
    return "\n".join(ops).encode("latin-1", "replace")


def write_pdf(path: Path, pages: list[str]) -> None:
    """Write a simple text-only PDF with one string per page."""
    objs: list[bytes] = []
    n = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
        stream = _page_stream(text)
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_W} {_H}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode()
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for num, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % num + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))


def main() -> None:
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for name, pages in DOCS.items():
        write_pdf(config.DOCS_DIR / name, pages)
        print(f"wrote {config.DOCS_DIR / name} ({len(pages)} pages)")


if __name__ == "__main__":
    main()
