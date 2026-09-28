# Cadet Tutor: 3-minute demo

A timed script with the exact text to type and what should appear. The answers
come from the local model, so the wording varies between runs, but the facts,
the citations and the refusals below should not. Rehearse it once before
presenting.

## Before you start (not part of the 3 minutes)

1. Make sure both models are installed: `ollama list` shows `qwen2.5:7b` and `bge-m3`.
2. **Turn Wi-Fi off** (and unplug Ethernet). Leave it off for the whole demo.
3. From the `cadet_tutor` folder: `streamlit run app.py`. The browser opens at
   `http://localhost:8501`.
4. Click **Demo** in the sidebar. You should see **"Demo loaded."** and
   "4 chunks indexed". The user is reset to **Cadet**.

## Script

### 0:00 – Introduction (15 s)
> "This is an AI instructor that runs entirely on this laptop. Wi-Fi is off.
> It answers only from our own documents, and it knows who is allowed to see what."

Point to the sidebar: **Signed in as Cadet**, **Clearance: Public (level 0)**.

### 0:15 – Grounded answer with a citation (30 s)
Tab **Ask**, type:

```
How must wounded and sick enemy soldiers be treated?
```

**Expect:** they must be respected and protected in all circumstances, treated
humanely and cared for; only urgent medical reasons justify priority in
treatment. Cited as **[geneva_conventions_extracts, p.1-2]**.

Open **Sources**: only Public documents are listed.

### 0:45 – Clearance: the Cadet is refused (20 s)
Type:

```
What is the H-hour for Exercise Iron Cedar?
```

**Expect:** *"I can't find this in the documents available at your clearance level."*
Open **Sources**: only `geneva_conventions_extracts` and `five_paragraph_order_guide`.
The confidential exercise order never reached the model.

### 1:05 – Same question as Instructor (25 s)
Sidebar: switch **Signed in as** to **Instructor** (Confidential, level 2).
Ask the same question again:

```
What is the H-hour for Exercise Iron Cedar?
```

**Expect:** **0530 on D+1**, cited as **[exercise_iron_cedar_opord, p.1]**.
> "Same question, same system, different clearance, different answer."

*(Optional if time allows: as **Officer**, ask
`What is the sentry challenge-and-reply procedure at night?` and expect the
procedure from **[platoon_sop_restricted, p.1]**, and a refusal for the Iron
Cedar question.)*

### 1:30 – Quiz (40 s)
Tab **Quiz**. Topic:

```
treatment of prisoners of war
```

Set **Questions** to `3`, click **Generate**. Answer them, click **Submit answers**.

**Expect:** a score out of 3, and for each question the correct answer, a short
explanation and its source label. Questions are only drawn from documents the
current user may see.

### 2:10 – Order review (40 s)
Tab **Order review**.

1. **Or load a sample order → Excellent**, click **Assess order**.
   **Expect:** a high total (roughly 75–100 / 100) with mostly full bars.
2. **Or load a sample order → Missing sections**, click **Assess order**.
   **Expect:** a low total (roughly 20–45 / 100). **Service Support** and
   **Command and Signal** score at or near 0, and the feedback says they are missing.

> "Same rubric, same grader: it rewards a complete order and names exactly what's missing."

The **Average** sample should land in between if you have time for a third run.

### 2:50 – Close (10 s)
Point at the Wi-Fi icon.
> "Everything you just saw ran on this machine, with no network."

## If something goes wrong

| Symptom | Fix |
|---|---|
| "Cannot reach Ollama" | Start Ollama (`ollama serve` or open the app), then refresh. |
| "Model … is not installed" | Needs a network once: `ollama pull <model>`, then turn Wi-Fi off again. |
| Old conversation or order still on screen | Click **Demo** again: it reloads the data and resets the app to Cadet. |

## How offline operation was verified

- `pytest tests/test_demo_offline.py` runs the whole demo through the app with the
  real Ollama client pointed at a fake Ollama on localhost. The test fails if
  anything opens a connection to, or looks up, any non-local address.
- The app was also run as a real process inside a Linux network namespace with no
  network except loopback, and driven in Chromium: Demo, Cadet refusal, Instructor
  answer and order grading all worked, and the browser made no requests outside
  `localhost`.
- ChromaDB telemetry is switched off in code, and `.streamlit/config.toml` turns off
  Streamlit's usage statistics and serves the app on `localhost` only.
