---
name: my-checklist
description: Write or update the user's own to-do list for a Kami phase (plans/phase-N/your-checklist.md) with the user-checklist agent — what only the user has to do, how, and where, in simple English. Use when every task in a phase is finished, or when the user asks what they have to do themselves.
argument-hint: "[phase number, default: the phase being worked on]"
---

# My checklist

Phase: `$ARGUMENTS`. If it's empty, use the phase of the most recent task worked on in this
session; otherwise the first phase in `MILESTONES.md` that isn't ✅.

1. Run the `user-checklist` agent with the phase number. If this session built tasks, include
   each `/dev-loop` wrap-up (files changed, QA result, the **Try by hand** steps), so nothing a
   builder or QA asked the user to check gets lost.
2. Show the user its report: the file link, how long it takes, and the 1–3 steps to do first.
   Don't paste the whole checklist; link it: `plans/phase-<N>/your-checklist.md`.
3. Leave the file uncommitted.
