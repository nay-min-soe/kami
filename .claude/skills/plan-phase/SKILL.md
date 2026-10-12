---
name: plan-phase
description: Plan a Kami phase with the agent team — phase-planner writes plans/phase-N/ (README + task files split into Backend and Frontend parts), plan-reviewer reviews it, looping until approved, then hands each task to /dev-loop. Use when the user asks to plan, create tasks for, or break down a phase from MILESTONES.md.
argument-hint: "<phase number>"
---

# Plan phase

Phase: `$ARGUMENTS`. If it's empty, read `MILESTONES.md` and ask which phase, suggesting the
first one without a `plans/phase-<N>/` folder.

You (the main session) are the orchestrator. Don't write plan files yourself.

```
phase-planner ─► plan-reviewer ──APPROVED──► user ─► /dev-loop task-1 ─► /dev-loop task-2 …
      ▲               │                               (backend-dev, frontend-dev,
      │        CHANGES NEEDED                          qa-tester, bugfix-dev)
      └───────────────┘   (max 3 rounds)
```

## Steps

1. **Check the ground.** If `plans/phase-<N>/` exists, tell the user the planner will
   *revise* it (finished tasks stay as they are). Offer `/backup` first.

2. **Plan, round n** (start at 1). Run `phase-planner` with the phase number and, from
   round 2 on, the reviewer's full report.

3. **Review.** Run `plan-reviewer` with the phase number, the round number, and the planner's
   report. Read its last line:
   - `VERDICT: APPROVED` → step 4.
   - `VERDICT: CHANGES NEEDED (…)` → back to step 2 with n + 1.
   - **Stop and ask the user** after 3 rounds without approval, or if the same Must-fix item
     comes back twice. Show the open items.

4. **Show the user.** The task table (task, size, owner, depends on), the suggested order,
   the **Open questions**, the reviewer's open Should-fix items, and anything in
   `your-checklist.md` they need to do. Ask them to answer the open questions or approve. If
   they change something, run one more planner → reviewer round with their notes.

5. **Hand over to the builders.** When the user approves, say which task comes first and that
   `/dev-loop plans/phase-<N>/task-<K>-<slug>.md` builds it. Run one task at a time, in the
   suggested order, and start a task only when the user asks. Leave the plan uncommitted and
   suggest `add phase <N> task plans`. When the last task is built, `/dev-loop` runs
   `/my-checklist <N>` to write the user's own to-do list for the phase.

## Who's who

| Agent | Nickname | Does | Links to |
|---|---|---|---|
| `phase-planner` | The Cartographer | writes `plans/phase-N/`, each task with **Owner** + Backend/Frontend parts + Contract | its parts are the work orders for backend-dev and frontend-dev |
| `plan-reviewer` | The Editor | read-only; checks fit, truth, buildability, safety, tests | gives a verdict back to phase-planner |
| `user-checklist` | The Guide | writes `plans/phase-N/your-checklist.md`: what only the user must do, how, where | runs after the last /dev-loop of the phase, or any time via `/my-checklist` |
