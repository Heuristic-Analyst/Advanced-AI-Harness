# Advanced AI Harness, from scratch

Builds upon [Basic AI Harness](https://github.com/Heuristic-Analyst/Basic-AI-Harness)

run either "main.py" for cli version or "gui.py" (files are not shown in gui, still in the shared folder).

Difference to Basic AI Harness version:
- has a gui
- agent can choose a sandbox (Podman), has a shared folder, mounts to Shared Folder/Common for exchange of files and Shared Folder/Notebook_Engine (read-only) to run Python Notebooks (tools included)
- can create new Project folders and mount several of them at once
- read-only projects (`READONLY_PROJECTS` in config.py): the agent can use them, never change them
- a browser: the `browser` sandbox + the `Browser` project, built on [agent-browser](https://github.com/vercel-labs/agent-browser). you can watch it live and take over (see Shared Folder/Browser/README.md)
- per-sandbox settings you write and the agent can't change: memory, cpus, GPU, a "view" port (Sandboxes/README.md)
- files in Shared Folder can't be executed directly, only through an interpreter (python x.py), and only inside the sandbox
- network can only be enabled or disabled by the user using /sandbox net on or off
