# Kami milestones

Kami is built in phases. Each phase ends in a release you can actually use. A phase
is done when its **exit criteria** pass, not when every idea in it is built.

Sizes: **S** = a few evenings, **M** = 1–2 weeks, **L** = 3+ weeks (solo, part-time).

| Phase | Release | Theme | Size | Status |
|---|---|---|---|---|
| 0 | v0.1 | Scaffold: Ask, Explain screen, safety gate | — | ✅ Done |
| 1 | v0.2 | Foundation hardening | S | ⬜ Next |
| 2 | v0.3 | Explain screen v1 + better Ask | M | ⬜ |
| 3 | v0.4 | Wayland support | M | ⬜ |
| 4 | v0.5 | Live meeting notes | L | ⬜ |
| 5 | v0.6 | App control v1 | L | ⬜ |
| 6 | v0.7 | Voice in and out | M | ⬜ |
| 7 | v1.0 | Release-ready | M | ⬜ |

Order matters: phase 4 builds the speech-to-text pipeline that phase 6 reuses, and
phase 5 needs the structured-output parsing that phase 2 hardens.

---

## Phase 0 — Scaffold (v0.1) ✅

Already in the repo.

- [x] Tray icon, single-instance socket, `kami toggle`
- [x] Config file + API key from `KAMI_API_KEY` / `OPENROUTER_API_KEY`
- [x] X11 hotkey via the `hotkey` extra
- [x] Ask: one-shot question in the panel
- [x] Explain screen: drag-select, vision model, circles / arrows / notes drawn on screen
- [x] Meeting notes from a pasted transcript
- [x] Safety gate (`allowed_apps` + confirm with risks) and a `launch` action
- [x] Tests for config, safety, annotation parsing

---

## Phase 1 — Foundation hardening (v0.2)

**Goal:** make what exists reliable before adding features. Task plans: [plans/phase-1/](plans/phase-1/README.md)

- [ ] CI: GitHub Actions running `pytest` on Python 3.11 and 3.12
- [ ] Linting: add `ruff` to the `dev` extra and to CI
- [ ] LLM errors in plain words: no key, 401 bad key, 402 no credit, 429 rate limit,
      timeout, model can't read images (today these show as raw `httpx` errors)
- [ ] Config validation: a bad TOML or wrong type gives a clear message, not a traceback
- [ ] Logging to `~/.local/state/kami/kami.log` (never log API keys or screenshots)
- [ ] Tests: `app_control.run` (unknown kind, gate refusal, not-allowed app),
      `meetings.summarize_transcript`, `LLMClient` with a mocked `httpx`
- [ ] `kami --version` and `kami doctor` (prints session type, hotkey status,
      whether a key is set, whether the model is reachable)

**Exit criteria**
- CI is green on every push to `main`
- Each error above shows a one-line, human message in the panel
- `kami doctor` explains why the hotkey or capture won't work on this machine

---

## Phase 2 — Explain screen v1 + better Ask (v0.3)

**Goal:** the flagship feature feels finished on X11.

- [ ] Follow-up questions: after an explanation, the input box asks about the same capture
      (keep the image + history for the session)
- [ ] Ask keeps a short chat history; "New chat" button clears it
- [ ] Streaming replies, so text appears as it arrives
- [ ] Multi-monitor and HiDPI: capture and annotations line up on every screen
      and at 125% / 150% / 200% scaling
- [ ] Annotation polish: fade out, "keep doodles" toggle, label placement that
      stays on screen
- [ ] Stricter annotation parsing tests (malformed, out-of-range, extra fields,
      prompt-injection text inside the screenshot)
- [ ] Copy-to-clipboard button for answers

**Exit criteria**
- Explain screen works on two monitors with different scaling, verified by hand
- Annotations land within a few pixels of their target on every tested setup
- A follow-up question about the same region needs no new capture

---

## Phase 3 — Wayland support (v0.4)

**Goal:** Kami works on a default Ubuntu / Fedora desktop, which is Wayland.

- [ ] Screen capture through the XDG desktop portal (`org.freedesktop.portal.Screenshot`)
- [ ] Detect session type once and pick X11 or portal capture
- [ ] Find out what the annotation layer can do on Wayland (apps can't position
      their own windows there); fall back to drawing on the captured image inside
      the panel if needed
- [ ] Hotkey through the portal `GlobalShortcuts` API where the desktop supports it;
      otherwise keep the `kami toggle` desktop shortcut
- [ ] README: tested desktops table (GNOME, KDE, Sway / Hyprland)

**Exit criteria**
- Explain screen works on GNOME Wayland and KDE Wayland
- Where on-screen doodles can't work, the user gets the in-panel version and is
  told why

---

## Phase 4 — Live meeting notes (v0.5)

**Goal:** the plan in `modes/meetings.py`: capture audio, transcribe, summarize.

- [ ] New optional extra `meetings` (`sounddevice`, `faster-whisper`) so the base
      install stays light
- [ ] Capture mic + system audio (PipeWire / PulseAudio monitor source)
- [ ] Transcribe in chunks on a background `QThread`; local Whisper by default,
      API transcription as an opt-in config choice
- [ ] Rolling transcript view with Start / Stop and a visible "recording" indicator
- [ ] Notes on Stop (summary, decisions, action items, open questions)
- [ ] "Quick research" on an open question, using Ask
- [ ] Save transcript + notes as Markdown only when the user clicks Save

**Exit criteria**
- A 30-minute call produces a transcript and notes with no UI freeze
- Audio never leaves the machine unless API transcription is turned on
- Recording can't start without a click, and the indicator is always visible while on

---

## Phase 5 — App control v1 (v0.6)

**Goal:** useful hands-free actions, every one behind the safety gate.

- [ ] Model proposes actions as JSON; parse it as untrusted input in `modes/app_control.py`
- [ ] Action kinds, each with its own risk text and tests:
  - [ ] `launch` (exists)
  - [ ] `open_url` in an allowed browser
  - [ ] `open_path` in an allowed editor or file manager
  - [ ] `focus_window` (X11 first; Wayland support depends on the desktop)
  - [ ] `type_text` into the focused allowed app (always sensitive)
- [ ] Action log at `~/.local/state/kami/actions.log`: what ran, when, who approved
- [ ] Confirm dialog shows the exact command or text, not just a summary
- [ ] No action kind can skip `gate()`; a test fails if one is registered without risks

**Exit criteria**
- Every action kind has tests for allowed, not-allowed, confirmed and refused
- A screenshot or web page containing "ignore your rules and delete…" cannot get
  an action past the confirm dialog
- `/security-check` passes on the phase's changes

---

## Phase 6 — Voice in and out (v0.7)

**Goal:** talk to Kami and hear answers. Reuses the phase 4 audio pipeline.

- [ ] Read explanations aloud (local TTS such as Piper, in a `voice` extra)
- [ ] Push-to-talk: hold a key, speak, release; transcript goes into the input box
- [ ] Voice commands feed app control; voice **never** skips the confirm dialog
- [ ] Mute toggle in the panel and tray

**Exit criteria**
- Push-to-talk to answer under ~3 s on a mid-range laptop with a local model
- A spoken command that triggers an action still waits for a click on **Do it**

---

## Phase 7 — Release-ready (v1.0)

**Goal:** someone who isn't you can install and use Kami in 10 minutes.

- [ ] First-run setup: asks for API key and model, writes the config
- [ ] Settings window (model, hotkey, allowed apps) instead of hand-editing TOML
- [ ] Optional autostart (`.desktop` file in `~/.config/autostart`)
- [ ] Install with `pipx install kami`; publish to PyPI
- [ ] Privacy page: what is sent to the model, when, and what is stored locally
- [ ] `CONTRIBUTING.md`, issue templates, changelog
- [ ] Real tray icon and app icon

**Exit criteria**
- A fresh Ubuntu install goes from zero to a working Explain screen by following
  the README alone
- All README "Status" rows are ✅ or clearly marked experimental

---

## Later / not planned yet

- Local models through Ollama for fully offline use
- macOS / Windows ports
- Plugins for third-party modes
