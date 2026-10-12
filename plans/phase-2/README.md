# Phase 2 — Explain screen v1 + better Ask (v0.3)

Goal: the flagship feature feels finished on X11. See [MILESTONES.md](../../MILESTONES.md).

Baseline (2026-10-08): 81 tests pass, `ruff` is clean, CI is green. Ask is one-shot
(no history), replies appear all at once, the panel always opens on the primary
screen, and `parse_lesson` crashes on 4 kinds of malformed model JSON (raw Python
text such as `slice(None, 4, None)` reaches the panel).

## Tasks

| # | Task | Size | Depends on |
|---|---|---|---|
| 1 | [Stricter annotation parsing + injection-safe output](task-1-annotation-parsing.md) | S | — |
| 2 | [Copy-to-clipboard button](task-2-copy-button.md) | S | — |
| 3 | [Chat history for Ask + "New chat"](task-3-chat-history.md) | M | — |
| 4 | [Follow-up questions about the same capture](task-4-follow-ups.md) | S | 3 |
| 5 | [Streaming replies](task-5-streaming.md) | M | 3 |
| 6 | [Multi-monitor and HiDPI](task-6-multi-monitor-hidpi.md) | M | — |
| 7 | [Annotation polish](task-7-annotation-polish.md) | S | 6 |
| 8 | [Type your question after the capture](task-8-ask-after-capture.md) | S | 4 |

Suggested order: 1 → 2 → 3 → 4 → 5 → 6 → 7.

- Task 1 comes first. It fixes real crashes, and Phase 5 (app control) relies on
  this parser style for untrusted model JSON.
- Task 2 is a small warm-up in `overlay.py` before Tasks 3–5 reshape the panel.
- Tasks 3 → 4 → 5 build on each other: history, then a capture inside the history,
  then streaming into it.
- Tasks 6 and 7 need an X11 session and a second monitor (see "Needs from you"). You
  can start them whenever that hardware is ready. Task 6 doesn't depend on 1–5.

## Rules for every task

Same as [Phase 1](../phase-1/README.md#rules-for-every-task), plus:

- One branch and one PR per task. Commit messages are lowercase and imperative.
- Code in `modes/`, `llm/`, `config.py`, `safety.py` and the new `conversation.py` /
  `geometry.py` stays free of Qt, so `pytest` runs without a display. Put logic there
  and keep `ui/` thin. UI behaviour is checked by hand (each task has a "Manual check").
- **Chat text and screenshots live in memory only.** Never write them to disk or to
  the log. Log counts and durations, never content (same rule as Phase 1 Task 5).
- Run `/security-check` on tasks that touch `llm/`, model output shown in the UI, or
  the screenshot (1, 3, 4, 5).
- Update `README.md` / `ARCHITECTURE.md` when behaviour or a component changes
  (`/docs-sync`, `/task-recap`).

## Phase exit criteria

- [ ] Explain screen works on two monitors with different scaling, verified by hand
- [ ] Annotations land within a few pixels of their target on every tested setup
- [ ] A follow-up question about the same region needs no new capture

## Needs from you

Step by step, with links and commands: **[your-checklist.md](your-checklist.md)**.

- **An X11 session.** Your desktop is GNOME on Wayland, where screen capture comes back
  black (that's Phase 3). At the login screen, click your name, then the gear icon,
  and pick **"Ubuntu on Xorg"** (or "GNOME on Xorg").
- **A second monitor** for Task 6. Ideally one is HiDPI. If not, Task 6 explains how
  to fake a different scale per screen with `QT_SCREEN_SCALE_FACTORS`.
- A little OpenRouter credit for the manual checks (each costs well under a cent).

## Decisions (2026-10-08)

1. **"Different scaling" on X11: use the Qt workaround for now.** GNOME and KDE on
   Xorg use one scale for all monitors; true per-monitor scaling is mostly a Wayland
   feature. For v0.3, the first exit criterion is met with Qt's per-screen scale
   (`QT_SCREEN_SCALE_FACTORS`). Proper per-monitor scaling comes later (Phase 3,
   Wayland).
2. **Follow-ups are text-only in v0.3.** Only the first explanation draws doodles.
   Follow-up answers are plain text (which lets them stream), and the first
   explanation's doodles stay on screen. New doodles for follow-ups come later.

## Closing the phase

When all three exit criteria are ticked: bump the version to `0.3.0` in
`src/kami/__init__.py` and `pyproject.toml` (own PR: `bump version to 0.3.0`), tag
`v0.3.0`, and set Phase 2 to ✅ in [MILESTONES.md](../../MILESTONES.md).
