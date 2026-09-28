"""A tiny stand-in for the Ollama HTTP API, served on localhost for offline tests.

It speaks just enough of /api/tags, /api/embed and /api/chat for the real
`ollama` client to work. Answers are canned; this checks wiring, not quality.
"""
import hashlib
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from src import config


def bow_vector(text: str, dims: int = 64) -> list[float]:
    """Deterministic bag-of-words embedding: similar words, similar vectors."""
    v = [0.0] * dims
    for w in text.lower().split():
        v[int(hashlib.md5(w.strip(".,:;()?").encode()).hexdigest(), 16) % dims] += 1.0
    return v


def fake_chat(messages: list[dict], json_mode: bool) -> str:
    prompt = messages[-1]["content"]
    if json_mode and "Rubric:" in prompt:
        ids = re.findall(r"^- (\w+) \(", prompt, re.M)
        return json.dumps({"criteria": [{"id": i, "score": 5, "feedback": "ok"} for i in ids],
                           "overall": "Fake assessment."})
    if json_mode:
        return json.dumps({"questions": []})
    labels = re.findall(r"^\[[^\]]+, p\.\d+(?:-\d+)?\]$", prompt, re.M)
    if not labels:
        return "I can't find this in the documents available at your clearance level."
    # Echo the first excerpt so tests can see exactly what the model was given.
    first = prompt.split(labels[0], 1)[1].strip().split("\n\n")[0]
    return f"{first[:300]} {labels[0]}"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep test output quiet
        pass

    def _send(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        models = [config.LLM_MODEL, f"{config.EMBED_MODEL}:latest"]
        self._send({"models": [{"model": m, "name": m} for m in models]})

    def do_POST(self) -> None:
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if self.path == "/api/embed":
            texts = req["input"] if isinstance(req["input"], list) else [req["input"]]
            self._send({"model": req["model"], "embeddings": [bow_vector(t) for t in texts]})
        elif self.path == "/api/chat":
            content = fake_chat(req["messages"], req.get("format") == "json")
            self._send({"model": req["model"], "created_at": "2026-01-01T00:00:00Z", "done": True,
                        "message": {"role": "assistant", "content": content}})
        else:
            self.send_error(404)


def start() -> tuple[ThreadingHTTPServer, str]:
    """Start the fake server on a free localhost port; returns (server, host URL)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
