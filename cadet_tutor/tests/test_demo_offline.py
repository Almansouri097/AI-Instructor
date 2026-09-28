"""Phase 8: demo mode works end to end and never touches the network.

The real `ollama` client talks to a fake Ollama on 127.0.0.1, and every socket
connection or DNS lookup to anything non-local is recorded and fails the test.
"""
import ipaddress
import socket

import ollama
import pytest
from streamlit.testing.v1 import AppTest

from src import config, demo, ingest, llm
from tests import fake_ollama

LOCAL_NAMES = {"localhost", "127.0.0.1", "::1", None}


def _is_local(host) -> bool:
    if host in LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture()
def offline(tmp_path, monkeypatch):
    """Isolated data dirs, fake Ollama, and a guard that records outside traffic."""
    attempts: list[str] = []
    real_connect, real_getaddrinfo = socket.socket.connect, socket.getaddrinfo

    def guarded_connect(self, address):
        host = address[0] if isinstance(address, tuple) else None
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(host):
            attempts.append(f"connect {address}")
            raise OSError("network disabled in test")
        return real_connect(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if not _is_local(host):
            attempts.append(f"dns {host}")
            raise socket.gaierror("network disabled in test")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)

    (tmp_path / "docs").mkdir()
    monkeypatch.setattr(config, "DOCS_DIR", tmp_path / "docs")
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(config, "LEVELS_CSV", tmp_path / "levels.csv")
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)

    server, host = fake_ollama.start()
    monkeypatch.setattr(config, "OLLAMA_HOST", host)
    monkeypatch.setattr(llm, "_client", ollama.Client(host=host))
    yield attempts
    server.shutdown()


def test_sample_orders_differ_in_completeness():
    orders = {name: demo.sample_order(name).upper() for name in demo.SAMPLE_ORDERS}
    for heading in ["SITUATION", "MISSION", "EXECUTION", "SERVICE SUPPORT", "COMMAND AND SIGNAL"]:
        assert heading in orders["Excellent"] and heading in orders["Average"]
    assert "SERVICE SUPPORT" not in orders["Missing sections"]
    assert "COMMAND AND SIGNAL" not in orders["Missing sections"]
    assert "COMMANDER'S INTENT" in orders["Excellent"] and "COMMANDER'S INTENT" not in orders["Average"]


def test_demo_load_sets_levels_and_ingests(offline):
    config.LEVELS_CSV.write_text("filename,level\nmy_notes.pdf,1\nexercise_iron_cedar_opord.pdf,0\n")
    demo.load()
    levels = ingest.load_levels()
    assert levels["exercise_iron_cedar_opord.pdf"] == 2  # demo level enforced
    assert levels["my_notes.pdf"] == 1  # user rows kept
    metas = ingest.get_collection().get(include=["metadatas"])["metadatas"]
    assert {m["doc"] for m in metas if m["level"] == 2} == {"exercise_iron_cedar_opord.pdf"}
    assert offline == []


def _button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def _app() -> AppTest:
    return AppTest.from_file(str(config.ROOT / "app.py"), default_timeout=60)


def test_full_demo_runs_offline(offline):
    at = _app().run()
    assert "store is empty" in at.warning[0].value

    _button(at, "Demo").click().run()
    assert not at.exception
    assert at.sidebar.selectbox[0].value == "Cadet"
    assert "Demo loaded" in at.sidebar.success[0].value

    # Cadet asks about the confidential exercise: the marker word must never reach them.
    at.chat_input[0].set_value("What is the H-hour for Exercise Iron Cedar?").run()
    cadet_text = " ".join(m.value for m in at.markdown)
    assert "NIGHTJAR" not in cadet_text and "exercise_iron_cedar_opord" not in cadet_text

    # Instructor asks the same question and gets the level-2 document.
    at.sidebar.selectbox[0].select("Instructor").run()
    at.chat_input[0].set_value("Iron Cedar H-hour 0530 NIGHTJAR").run()
    assert "exercise_iron_cedar_opord" in " ".join(m.value for m in at.markdown)

    # Sample order loads into the text box and can be graded.
    at.selectbox(key="sample_order").select("Missing sections").run()
    assert at.text_area(key="order_text").value.startswith("ORDERS FOR BRIDGE ATTACK")
    _button(at, "Assess order").click().run()
    assert not at.exception
    assert any("/100" in m.value for m in at.metric)

    # Demo again resets everything back to a clean Cadet session.
    _button(at, "Demo").click().run()
    assert at.sidebar.selectbox[0].value == "Cadet"
    assert at.text_area(key="order_text").value == ""

    assert offline == [], f"network access attempted: {offline}"
