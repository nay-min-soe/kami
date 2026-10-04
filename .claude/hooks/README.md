# Hooks → skills

Each hook nudges Claude toward the skill that fits the moment. Hooks only add context
(or, for `backup_guard`, ask the user); the skills do the work. Wired in `../settings.json`.

| Hook | Event | Fires when | Skill it points to |
|---|---|---|---|
| `skill_suggest.py` | UserPromptSubmit | prompt mentions brainstorming, a new feature, security, review, cleanup, backup | brainstorm, architecture-advisor, security-check; suggests /kami-review, /clean-code, /backup |
| `explain_first.py` | PreToolUse `Edit\|Write` | first edit to `src/`, `tests/`, `pyproject.toml` in each prompt | explain-first (and /backup for big changes) |
| `backup_guard.py` | PreToolUse `Bash` | `rm -rf`, `git reset --hard`, `git clean -f`, `git restore`, force push… | asks the user; suggests /backup |
| `docs_reminder.py` | PostToolUse `Edit\|Write` | edit to `src/kami/**.py` or `pyproject.toml` | docs-sync, then /kami-review |
| `security_reminder.py` | PostToolUse `Edit\|Write` | edit to `safety.py`, `config.py`, `app.py`, `app_control.py`, `llm/`, `ui/confirm.py`, `pyproject.toml` | security-check |

`/kami-review`, `/clean-code` and `/backup` have `disable-model-invocation`, so hooks can
only tell Claude to suggest them; the user runs them.

Test a hook by piping an event into it:

```bash
echo '{"prompt":"how should I build voice input?"}' | python3 .claude/hooks/skill_suggest.py
```
