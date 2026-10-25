---
name: sandbox
description: Use before you run code, install packages, or create, read or change files, and before you create, mount, rename or delete a project.
---

# Working in the sandbox

The sandbox is a throwaway Linux container. Everything you run happens there, never on the user's computer: you have no other way to run anything. You are root inside it.

## What is kept and what is not

- `/workspace/Common` = the user's `Shared Folder/Common`. Kept. Every running instance of this program sees it too, so other instances may be working in it.
- `/workspace/<project>` = the user's `Shared Folder/<project>`, if one is mounted. Kept. Only you can mount it while you have it.
- `/workspace/Notebook_Engine` = the program that runs notebooks. Read-only: never put anything there.
- Everything else inside (installed packages, files in /tmp or /root, running programs) is gone when the sandbox stops or restarts.
- Files in /workspace can't be executed directly: run them with an interpreter (`python x.py`, `bash x.sh`).

## Steps

1. **Look first.** Your system prompt says what ran when this context started; later tool results are newer. If unsure: `check_sandbox` (which sandbox runs, what each one contains) and `check_projects`.
2. **Pick the project before you start.** Does the work belong to a project? Use an existing one, or `create_project` (only if none fits). Give it to `open_sandbox(name, project)` right away: `mount_project` and `unmount_project` restart the sandbox, which loses installs, running programs and open notebooks. No project: work in `/workspace/Common`.
3. **Pick the sandbox by its Containerfile.** It is exactly what you get. Notebooks need one with python3 (e.g. `python`).
4. **Work with sandbox_shell.** Small steps, read what each command prints. Big output: write it to a file in /workspace and search it with grep, instead of printing it all.
5. **Long jobs** (over the time limit): start them in the background with their output in a file, `nohup python job.py > job.log 2>&1 &`, then check the file.
6. **When done**, tell the user where the results are, as paths on their computer: `Shared Folder/<project>/...` or `Shared Folder/Common/...`.

## Good to know

- The network is off. Installing (`pip install`, `apt-get install`) needs it, and only the user can switch it on (`/sandbox net on`). Ask them, and say what you want to install. If a package is needed often, suggest adding it to the sandbox's Containerfile, so it is there at every start.
- One sandbox per instance. To switch, `close_sandbox`, then `open_sandbox`.
- A project mounted by another instance can't be mounted, renamed or deleted now: pick another one, or tell the user.
- Never delete or rename a project unless the user asked for it.
- After a checkpoint, your notes don't need to repeat what runs (the system prompt shows that), but they must say which files and notebooks matter and what each one is for.
