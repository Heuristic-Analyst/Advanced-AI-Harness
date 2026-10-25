# Ego

Who the assistant is. Everything in here is written by you; the assistant only reads it.

| File | What it is |
|---|---|
| `SOUL.md` | Who the assistant is and how it works: the start of its system prompt. |

## SOUL.md

The system prompt is the first message of every conversation, and the model reads it before anything else. It is built from parts, and the soul is always the first one:

```
system prompt
  1. SOUL.md                  <- this file
  2. the skills menu          (from skills/)
  3. the checkpoint           (once there is one)
```

So whatever you write here, the assistant follows in every conversation: its name and role, its tone, how long its answers are, what it should always or never do.

- **Read at the start.** `main.py` reads it once, when the program starts. Change it, then start the program again. A conversation you `/open` again gets the new version too, because its system prompt is built fresh.
- **Missing or empty?** Then the system prompt starts with `You are a helpful assistant.` instead.
- **It costs on every call.** The whole system prompt is sent with every message to the model. Keep the soul short: a few clear lines work better than a long text.
- **Plain markdown.** Headers and bullet points are fine. No special format is needed, and no header between `---` lines (that's only for skills).

## Writing a good soul

- **Say who it is and who it works for.** "You are a personal assistant running on your user's own computer."
- **Say how it should answer.** Short or detailed, simple words or technical, answer first or explain first.
- **Say what to do when unsure.** "If you don't know something, say so instead of guessing."
- **Name its tools only in general.** The model already gets every tool's description, so "use your tools instead of guessing" is enough. Never mention a tool that doesn't exist: the model will try to use it.
- **Leave out step-by-step instructions for one kind of task.** Those belong in a skill (`skills/`), which is only loaded when needed.