---
name: projects
description: Use when work belongs to a project or takes more than a few steps. Keep a PROJECT.md scratchpad in the project folder (what it is, layout, how to run, decisions, state), so the next conversation starts up to speed.
---

# Projects and their scratchpad

A conversation is one context. It starts empty, it gets compressed when it fills up, and the next conversation knows nothing about it. What survives is what is on disk.

So a project keeps a scratchpad: `PROJECT.md` at its root. It holds what a fresh you would need - what the project is, how the files are laid out, how to run it, what was decided and why, where the work stands. One read of that file and a new conversation goes on, instead of starting over.

## When to use one

- Work that touches more than a file or two, or that will not fit in one answer: a project, with a PROJECT.md.
- A quick one-off (a calculation, a single command, a script you throw away): no project, no notes.

## Where the notes live

- `Shared Folder/<project>/PROJECT.md`, which is `/workspace/<project>/PROJECT.md` inside the sandbox. It is kept on the user's computer, so it outlives every conversation.
- Work that lives in Common and nowhere else: no scratchpad there. If it will take more than a few steps, make it a project first (create_project) and work in that.

## The first thing in a new conversation

1. Your system prompt says what runs and which projects exist, as of when this context started. Read it before anything else.
2. `check_projects` (which project is free to mount), then get it in: `open_sandbox` opens a sandbox and mounts the projects in one step (`projects=[...]`, add `Browser` if you will need the web), or `mount_project` if a sandbox already runs.
3. Read the notes before touching anything:
   sandbox_shell: `cat /workspace/<project>/PROJECT.md; ls -la /workspace/<project>`
4. Nothing there, but the folder already has work in it: write the scratchpad from what is actually on disk (find, read the files) before you change a thing. The next conversation needs that baseline.
5. Only now start the task.

## What goes in it

- **What this is**: a line or two. What the project is for, and what "done" means.
- **How to run it**: the exact commands, from inside the sandbox, that build, run and test it. Not "run the tests" - the command.
- **Layout**: the file tree, one line per important file or folder, saying what it is for. Take it from `find`, never from memory.
- **Decisions**: what was decided and why. This is the part a new you cannot guess, and the part that keeps finished work from being undone.
- **State**: what is finished, what is in progress, the very next step.
- **Gotchas**: what broke, what is slow, version quirks, where the data comes from.
- **Recent**: a few dated one-liners, newest first, five at most.

## Keeping it true

1. Read it, change the parts that changed, write the whole file back. It is short enough for that, and nothing gets lost between the sections.
2. Update it when files are created or moved (layout), when a decision is made (decisions), when a step is finished (state) - and always before you stop.
3. Before you finish a task, ask: if the context ended here, could the next one go on from this file alone? What is missing is what goes in.
4. Keep it short, under about 120 lines. Delete done items that no longer matter, keep the five newest log lines. It is read at the start of every conversation, so its length is a real cost.
5. Check what you wrote: `cat` it back or `wc -l` it, and make sure the tree in it matches what `find` returns right now.
6. Tell the user, in one line, where the notes are: `Shared Folder/<project>/PROJECT.md`.

## A checkpoint is not this

`checkpoint.md` is your own notes for your own context. The program asks for it when the conversation gets full, it lives in the conversation's folder, and the next conversation never sees it.

PROJECT.md is the other direction: on disk, in the project, for the user and for every conversation after this one. When you write a checkpoint, its "Files" section should point at PROJECT.md rather than repeat it.

## What not to put in it

- No secrets: no API keys, passwords or tokens. It is a plain file, and it is readable from inside the sandbox.
- No essays, no list of every command you ran, no code that can be read in the files themselves.
- Nothing unchecked. A layout that does not match the disk is worse than no layout.

## The template

```markdown
# <project>

What it is, and what "done" means.

## Run

    cd /workspace/<project>
    python main.py          # or: pytest, npm start, ...

## Layout

    find . -maxdepth 3 -type f -not -path './.git/*' | sort

- `main.py` - entry point, reads the CSV and writes report.csv
- `data/` - the exports from <where they come from>

## Decisions

- 2026-10-25: sqlite instead of csv, because the queries got joins.

## State

- done: import works, tests green
- now: the monthly summary
- next: add a --month flag

## Gotchas

- pandas 2 changed how dates are parsed; keep the format= argument.

## Recent

- 2026-10-25 - built the importer, wrote the first tests
```
