# Kami 👻

[![CI](https://github.com/nay-min-soe/kami/actions/workflows/ci.yml/badge.svg)](https://github.com/nay-min-soe/kami/actions/workflows/ci.yml)

**A hotkey-summoned AI sidekick for the Linux desktop.**
Press a key, Kami pops up. It helps in meetings, explains anything on your screen
by doodling on it like a teacher with a marker, and (carefully) controls your apps.

> Open and self-run: git clone it, bring your own OpenRouter (or other) API key,
> and choose exactly which apps Kami may touch.

## What it does

| Mode                     | What you get                                                                                                                                           | Status                                                             |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------ |
| **Ask**            | Type a question in the pop-up panel. The answer streams in as it's written (**Stop** ends it early). It remembers the chat (in memory only) until you click **New chat**; **Copy** puts the last answer (as Markdown) on the clipboard | ✅ Works                                                           |
| **Explain screen** | Drag a box around anything (a YouTube lesson, code, a chart), then type your question (or just press Enter to have it explained). Kami answers and draws circles, arrows and short notes **on the screen itself**. Doodles fade out after 25 s (**📌 Keep** holds them). Then type follow-up questions about the same capture (text answers, no new screenshot) | ✅ Works (X11; see Wayland notes)                                  |
| **Meeting notes**  | Transcripts, notes and quick research                                                                                                                  | 🟡 Notes from a pasted transcript work; live audio capture is TODO |
| **App control**    | Hands-free actions inside allowed apps                                                                                                                 | 🟡 Safety gate + "launch app" done; more actions TODO              |

## The safety rule

Kami never acts blind:

1. It only touches apps listed in `allowed_apps`.
2. Before any sensitive action it shows **what it wants to do and what could go wrong**,
   and waits for you to click **Do it** (the default button is **Nope**).

This lives in [`src/kami/safety.py`](src/kami/safety.py) and is covered by tests.

## Quick start

```bash
git clone https://github.com/<your-username>/kami.git
cd kami
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[hotkey,dev]"

mkdir -p ~/.config/kami
cp config.example.toml ~/.config/kami/config.toml
export OPENROUTER_API_KEY="sk-or-..."     # or KAMI_API_KEY

kami            # starts Kami (tray icon + panel)
```

Needs Python 3.11+. For **Explain screen**, set `model` in the config to a
vision-capable model from [https://openrouter.ai/models](https://openrouter.ai/models).

If the config file has a mistake (bad TOML, a wrong type such as `allowed_apps = "firefox"`
instead of `["firefox"]`), Kami won't start and tells you the file, the key and the fix.
Misspelled keys are reported as warnings in the terminal.

### Hotkey: X11 vs Wayland

- **X11:** the built-in listener uses `<ctrl>+<alt>+k` (change it in the config).
- **Wayland:** apps can't grab global keys. Add a custom shortcut in your desktop
  settings that runs `kami toggle`. Screen capture on Wayland may also need the
  XDG desktop portal; this is on the roadmap.

`kami toggle` also works on X11 and shows or hides the running instance.

### Several monitors and HiDPI (X11)

- The panel opens on the monitor under your mouse, and Explain screen works on the
  monitor you start the drag on (one box can't span two monitors).
- Big captures are shrunk to 1568 px on the long edge before sending, to save tokens.
- GNOME and KDE on Xorg use one scale for every monitor. To give Qt a different scale
  per screen, start Kami with, for example,
  `QT_SCREEN_SCALE_FACTORS="DP-1=1;HDMI-1=2" kami` (output names come from `xrandr`).
  Proper per-monitor scaling is planned for later.

## Project layout

```
src/kami/
  cli.py              command line: start, toggle, doctor, --version (no Qt needed)
  doctor.py           `kami doctor` health report
  app.py              tray icon, panel start-up, single-instance socket (`kami toggle`)
  config.py           ~/.config/kami/config.toml (validated) + env var API key
  conversation.py     short in-memory chat history for Ask
  geometry.py         screen maths for doodles and captures (no Qt)
  logs.py             log file with key redaction
  hotkey.py           global hotkey (X11 via pynput)
  safety.py           allowlist + confirm-before-sensitive-actions gate
  llm/client.py       OpenRouter / OpenAI-compatible chat client (text + images)
  modes/
    learning.py       explain-screen prompt + annotation parser
    meetings.py       transcript -> notes (capture TODO)
    app_control.py    action handlers behind the safety gate
  ui/
    overlay.py        the pop-up panel
    region_select.py  drag-to-select screen region
    annotation.py     click-through layer that draws circles, arrows, notes
    confirm.py        the "Kami wants to..." dialog
    worker.py         runs LLM calls off the UI thread
tests/                pytest suite (config, safety, app control, meetings, annotation parsing)
```

## Roadmap

The full phase-by-phase plan is in [MILESTONES.md](MILESTONES.md).

- [ ] Live meeting capture (PipeWire monitor + Whisper) with a rolling transcript
- [ ] Voice output for explanations
- [ ] Wayland screen capture via the XDG desktop portal
- [ ] Multi-monitor polish
- [ ] More app-control actions (each with its own risk description)
- [ ] Voice commands for hands-free control

## Troubleshooting

Run `kami doctor` first. It works without a display (e.g. over SSH) and prints what
works and what doesn't: session type, config, whether a key is set (never the key
itself), whether the endpoint and model answer, the hotkey, and screen capture. It
exits with 1 if anything is ✗, and it never sends a chat request, so it costs nothing.
`kami --version` prints the version.

Kami writes a log to `~/.local/state/kami/kami.log` (rotated at 1 MB). It records what
happened and how long it took, never your API key, screenshots, questions or answers.
For more detail, start Kami with `KAMI_LOG_LEVEL=DEBUG kami`.

Doodles in the wrong place? Start Kami with `KAMI_DEBUG_DOODLES=1 kami` and use Explain
screen: it skips the AI (no cost) and draws a test pattern, small circles on each corner
of your box and one in the middle, so you can see how far off they are.

## Development

```bash
pip install -e ".[dev]"
ruff check .     # lint
pytest           # tests
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs `pytest` on
Python 3.11 and 3.12, plus `ruff check .` once, for every push to `main` and every
pull request.

## License

MIT. See [LICENSE](LICENSE).
