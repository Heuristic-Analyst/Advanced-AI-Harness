---
name: notebook
description: Use when you work in a Jupyter notebook with the nb_* tools, for data analysis, step-by-step code, plots, or anything where variables should stay alive between steps.
---

# Notebooks

A notebook is a .ipynb file in one of the user's folders (Common/ or the mounted project), made of cells. While it is open, a kernel runs in the sandbox and keeps every variable: what one cell creates, later cells can use. Every change is saved to the file right away, so the user can open it at any time.

## When to use one

- Exploring or analyzing data, building something step by step, making plots: a notebook.
- A one-off command (install a package, list files, run a finished script): sandbox_shell instead.

## Before you start

- A sandbox with python3 must run (e.g. `python`). The plain `ubuntu` one has no python3.
- Where the notebook goes: into the project when the work belongs to one, otherwise into Common/. Mount the project BEFORE you open notebooks: mount_project and unmount_project restart the sandbox, and that closes every open notebook.

## How to work

1. Open it: nb_create for a new one (e.g. `website/stats/sales.ipynb` or `Common/sales.ipynb`, missing folders are created), nb_open for an existing one.
2. Make the first cell a markdown cell with the goal, the plan and what is done. Update it with nb_edit whenever a step is finished or the plan changes. It is how you, after a checkpoint, and the user see where the work stands and why each cell is there.
3. One step per cell, small enough to check its output. Add it with nb_add and run true, then read the output before the next step.
4. A cell fails or is wrong: fix that same cell with nb_edit and run true. Don't add a new cell for the fix.
5. A quick look you don't need later (df.head(), a test print): run it in a cell, then remove the cell with nb_remove.
6. When done: nb_rerun, so you know it works from top to bottom. Fix what fails, rerun, update the first cell, then nb_close.
7. Tell the user where the notebook is on their computer: `Shared Folder/` plus its path, e.g. `Shared Folder/website/stats/sales.ipynb`.

## What you get back

- nb_add, nb_edit, nb_run: the output of the cells this call ran, then the overview.
- nb_remove: a short confirmation, then the overview.
- nb_rerun: the output of every code cell, then the overview.
- nb_open and nb_show: everything, every cell with its full code and output.
- Each cell's output is cut after 4,000 characters; the rest is only in the file. Print summaries (shape, head, totals), not whole tables.
- Plots come back as a note that there is a figure. They are saved in the notebook.

nb_edit replaces the whole code of a cell. The overview shows only its first line, so before you edit a cell whose full code you haven't seen in this conversation, call nb_show.

## Reading the overview

Every answer ends with a list of all cells: number, id, state, first line. Use the ids from it; they stay the same when cells move.

- ran [n]: ran in this kernel. Fine.
- not run: never ran. Its variables don't exist yet.
- old output, not run in this kernel: the output is from an earlier session. Run it (or nb_rerun) before you rely on it.
- EDITED since, output is stale: the code changed after it ran. Run it again before you trust its output.
- error: it failed. Fix it before you go on.
- markdown: text, nothing to run.

"the notebook file was changed outside" means the user edited it. Read the overview again (nb_show for details). Never undo the user's changes.

## Good to know

- Notebook calls for the same notebook in one reply may run in any order. When order matters, one call per reply, or give nb_run several cell ids: they run in that order.
- The kernel's working folder is the notebook's folder: relative paths start there.
- input() doesn't work: there is no one to type.
- A cell that runs too long is stopped; the variables are kept. Long jobs: write a script and start it in the background with sandbox_shell.
- Packages: install them with sandbox_shell (pip install ...). That needs the network, which only the user can switch on. After the install, import works in the open notebook. Installs are gone when the sandbox stops.
- The kernel crashed (most often: out of memory) or the sandbox restarted: all variables are gone. nb_open the notebook, then nb_rerun or run the cells you need.
- "open in another running instance": the user runs this program more than once, and the other one has that notebook open. Use another notebook, or tell the user.
