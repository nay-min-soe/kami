---
name: dev-loop
description: Build a Kami task with the agent team — backend-dev and frontend-dev build it, qa-tester checks it, and bugfix-dev fixes what QA finds, looping QA ⇄ bugfix until QA passes. Use when the user asks to build or implement a Kami feature or a plans/phase-N task with the agents/team.
argument-hint: "<task, or path to a plans/phase-N/task file>"
---

# Dev loop

Task: `$ARGUMENTS`. If it's a path, read that file. If it's empty, ask the user what to build.

A task file written by `/plan-phase` has an **Owner** (backend / frontend / both), a
**Backend part**, a **Frontend part** and, for "both", a **Contract**. Use them in step 2:
each builder gets its own part plus the Contract, and QA checks the result against the whole
task file (Tests, Done when, Security).

You (the main session) are the orchestrator. The agents do the work; you pass reports between
them and talk to the user. Don't edit `src/` or `tests/` yourself during the loop.

```
brief ─► backend-dev ─► frontend-dev ─► qa-tester ──PASS──► recap ─► done
                                           ▲    │
                                           │  FAIL
                                           │    ▼
                                           └─ bugfix-dev   (max 3 fix rounds)
```

## Steps

1. **Brief.** Follow the **explain-first** skill: read the code, write the plain-English brief,
   and say which half each agent gets (backend, frontend, or both). For a change touching more
   than ~3 files, suggest `/backup` first. **Wait for Do it.** Nothing runs before that.

2. **Build.**
   - Task file with an **Owner** → follow it. Otherwise decide from the files involved.
   - Core-only task → `backend-dev`. UI-only task → `frontend-dev`.
   - Both, and the UI uses new core logic → `backend-dev` first, then `frontend-dev` with
     backend's report pasted into its prompt.
   - Both but independent (no shared files, no new API between them) → start them in parallel,
     in one message.

   Each agent's prompt holds: the approved brief word for word, the line "The user approved this
   brief with Do it", the task, and the file ownership it has. If an agent stops with an
   out-of-scope question, take it to the user before going on.

3. **QA, round n** (start at 1). Run `qa-tester` with the brief, the build reports, and, from
   round 2 on, the previous Must-fix list so it can check those are really fixed. Read the last
   line of its report:
   - `VERDICT: PASS` → step 5.
   - `VERDICT: FAIL (…)` → step 4.

4. **Fix.** Run `bugfix-dev` with the brief, the round number, and the QA report's **Must fix**
   section copied in full. Then go back to step 3 with n + 1.
   - **Stop the loop** and hand over to the user if any of these is true: QA has failed after
     3 bugfix rounds; the same finding comes back twice; bugfix-dev reports something out of
     scope; or bugfix-dev disputes a finding and QA still insists on it. Show the open findings
     and ask how to go on. Don't loop forever.

5. **Wrap up.**
   - Run the **task-recap** skill if this was a `plans/` task.
   - Tell the user, in three bullets: what changed, the QA result (rounds taken, Should-fix
     items left open), and the frontend's and QA's **Try by hand** steps.
   - Leave everything uncommitted. Suggest a commit message (imperative, lowercase, no period)
     and `/kami-review` if they want a second opinion.
   - If this was a `plans/phase-N/` task and every task in that phase's README is now built,
     run the **my-checklist** skill for phase N, so the user gets their own to-do list
     (merge, release, tests by hand) in simple English.

## Who's who

| Agent | Nickname | Owns | Preloaded skills |
|---|---|---|---|
| `backend-dev` | The Plumber | core logic: `cli.py`, `config.py`, `safety.py`, `llm/`, `modes/`, … + tests | security-check, docs-sync |
| `frontend-dev` | The Stagehand | UI: `app.py`, `hotkey.py`, `ui/` | security-check, docs-sync |
| `qa-tester` | The Skeptic | read-only; runs the kami-review checklist, pytest, ruff | security-check |
| `bugfix-dev` | The Surgeon | any file, but only to fix QA's Must-fix list | security-check, docs-sync |
