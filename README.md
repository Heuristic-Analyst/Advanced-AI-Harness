# Advanced AI Harness, from scratch

Builds upon [Basic AI Harness](https://github.com/Heuristic-Analyst/Basic-AI-Harness)

run either "main.py" for cli version or "gui.py" (files are not shown in gui, still in the shared folder).

Difference to Basic AI Harness version:
- has a gui
- agent can choose a sandbox (Podman), has a shared folder, mounts to Shared Folder/Common for exchange of files and Shared Folder/Notebook_Engine (read-only) to run Python Notebooks (tools included)
- can create new Project folders and mount to them
- Cannot execute anything in Shared Folder so everything is safe
- network can only be enabled or disabled by the user using /sandbox net on or off
