# skills

A skill is a set of step-by-step instructions for one kind of task, written for the model. The model only reads a skill when it needs it, so you can have many skills without making every request bigger.

| Skill | What it is for |
|---|---|
| `stepwise-calculation` | Calculations with more than one step: break them down, calculate each step with `calculate`, show every step. |
| `sandbox` | Running code and working with files and projects: what is kept, picking the project before opening, long jobs, the network. |
| `notebook` | Working in a Jupyter notebook with the `nb_*` tools: a plan cell, one step per cell, reading the overview. |

Without Podman, `main.py` removes the `sandbox` and `notebook` skills, together with their tools.

## How skills work

A skill has two parts, and the model sees them at different times:

1. **The menu: always.** The name and the one-line `description` of every skill are in the system prompt:
   ```
   You have skills: step-by-step instructions for certain kinds of tasks. When a task matches a skill,
   first call load_skill with its name, then follow what it returns.
   Skills:
   - stepwise-calculation: Use when a calculation needs more than one step, like ...
   ```
2. **The instructions: only when needed.** When a task matches, the model calls the `load_skill` tool with the skill's name, and gets the whole `SKILL.md` back. That stays in the conversation, so it reads it once per task.

So a long skill costs nothing until it is used. Only its description is sent with every request.

## How a skill looks

One folder per skill, with one file inside, always called `SKILL.md`:

```
skills/
└── stepwise-calculation/
    └── SKILL.md
```

The file starts with a header between two `---` lines, then the instructions:

```markdown
---
name: stepwise-calculation
description: Use when a calculation needs more than one step, like a word problem or a price with discount and tax.
---

# Stepwise calculation

1. ...
2. ...
```

| Header line | What it is |
|---|---|
| `name` | What the model calls the skill. Lowercase, `-` between words. Must be unique. Left out: the folder's name is used. |
| `description` | **Required.** One line saying *when* to use the skill. It is all the model knows about the skill until it loads it, so it decides whether the skill is ever used. Start it with "Use when ...". |

## How to make a new skill

1. Create a folder in here, named like the skill: `skills/my-skill/`.
2. Put a `SKILL.md` inside, with the header and the instructions.
3. Start `python main.py` again. The start line lists every skill it found:
   ```
   model: deepseek/deepseek-flash | tools: calculate, load_skill | skills: my-skill, stepwise-calculation
   ```

Nothing else has to change: `functions/load_skills.py` finds every skill by itself when the program starts.

## The rules the loader follows

- **Only `<folder>/SKILL.md` is a skill.** Files lying directly in here, like this README, are skipped, and so is a folder without a `SKILL.md`.
- **One `key: value` per header line.** The value is everything after the first `:`, on that one line. Quotes around it are removed.
- **Two skills with the same `name` stop the program** at start, naming both files.
- **A skill without a `description` stops the program** too: without one, the model would never know when to use it.
- **Skills are read once, at start.** A new or changed skill needs a restart.
- **No skills at all?** Then there is no menu in the system prompt, and the model doesn't get the `load_skill` tool either.

## Writing a good skill

- **The description decides everything.** The model picks a skill by its description alone. Say when to use it, in the words a user would use: "Use when the user asks for a commit message", not "Commit message guidelines".
- **Write for the model, in steps.** Numbered steps it can follow, what to watch out for, and what the answer should look like. Short sentences.
- **Refer to the tools.** A skill can tell the model which tool to use for which step, like `stepwise-calculation` does with `calculate`.
- **Keep it short.** A loaded skill stays in the conversation and is sent again with every later request in that task. Say what matters, leave out what the model already knows.
- **One skill, one kind of task.** Two different jobs are two skills, each with its own description.
- **`: ` in the description?** It works here, but GitHub shows the header as broken YAML. Put quotes around the description then: `description: "Use when: ..."`.
