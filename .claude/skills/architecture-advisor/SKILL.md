---
name: architecture-advisor
description: Recommend where and how a new Kami feature fits the architecture, from the user's feature idea or prompt. Use when the user describes a new feature, mode, integration, or asks "how should I build X".
argument-hint: "<feature idea>"
---

# Architecture advisor

Feature idea: `$ARGUMENTS` (if empty, use the user's latest message).

The output is a recommendation, not code. Write it in plain English; the user decides.

## Steps

1. **Restate** the feature in one sentence and list what you are assuming. If one unknown changes the whole design (e.g. "local or cloud speech-to-text?"), ask it now, and only that.
2. **Read the code the feature touches** — the layers below tell you which files. Base the advice on what is there now.
3. **Place it**: for each layer, say what the feature adds or changes there, or "no change".
4. **Give 2–3 options** with a real difference between them (e.g. new mode vs. extending an existing one; local vs. API; built-in vs. optional extra). For each: how it works in two sentences, good for, bad for, effort (S / M / L).
5. **Recommend one** and say why in two or three sentences.
6. **Smallest first slice**: the thinnest version that works end to end, as a list of files to create or change, plus the test that proves it (`tests/test_<module>.py`).
7. **Risks**: run the recommendation through the checks below and list the ones that apply.

Done when the user can pick an option and the first slice names every file it touches.

## Kami's layers

| Layer | Lives in | Rule |
|---|---|---|
| Entry & lifecycle | `app.py` | tray icon, single-instance socket, wiring only; no feature logic |
| Config | `config.py` + `config.example.toml` | a dataclass per section; every new key gets a default and an example comment |
| Input triggers | `hotkey.py`, `kami toggle` | X11 via pynput; Wayland users bind a desktop shortcut to a CLI command |
| Modes | `modes/<name>.py` | pure Python: prompt text, request building, output parsing. No Qt imports, so it is testable with `uvx pytest` |
| LLM | `llm/client.py` | one OpenAI-compatible client; modes call `ask` / `ask_about_image`, never `httpx` directly |
| UI | `ui/*.py` | Qt widgets only; call mode functions through `ui/worker.run_in_background` |
| Safety | `safety.py` | any action outside Kami's own windows passes `gate()`; each new action kind ships with its risk text |

## Checks for every recommendation

- **Main thread**: anything blocking (network, audio, OCR, model inference) goes through the worker or its own `QThread`.
- **Safety gate**: does it act on other apps or the filesystem? Then it needs a `ProposedAction` with real risks and a gate test.
- **X11 / Wayland**: hotkeys, screen capture, and window control differ. Wayland capture needs the XDG desktop portal (on the roadmap).
- **Dependencies**: heavy or platform-specific packages (audio, Whisper, OCR) go in an optional extra in `pyproject.toml`, like `hotkey`, so the base install stays light.
- **Privacy**: what user data leaves the machine, when, and whether the user triggered it.
- **Roadmap fit**: check `README.md` → Roadmap and module "Plan:" notes (e.g. `meetings.py` plans PipeWire + Whisper); build on the planned direction or say why to change it.
