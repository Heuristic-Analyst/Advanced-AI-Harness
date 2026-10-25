# Sandboxes

A sandbox is a throwaway Linux container ([Podman](https://podman.io)) where the agent runs everything: commands, installs, notebooks. It never runs anything on your computer itself.

| Sandbox | What it is |
|---|---|
| `python` | Python 3.12 with numpy, pandas and matplotlib. The one notebooks need. |
| `ubuntu` | Plain Ubuntu 24.04. No Python. |

## How a sandbox looks

One folder per sandbox, with one file inside, always called `Containerfile`. That file is all there is:

```
Sandboxes/
└── python/
    └── Containerfile
```

```dockerfile
FROM docker.io/library/python:3.12-slim
RUN pip install --no-cache-dir numpy pandas matplotlib
```

The folder's name is the sandbox's name: lowercase letters, digits and `-` only (Podman's rule for image names). The agent reads the Containerfiles (`check_sandbox`) to pick the sandbox that fits a task.

## What happens when the agent opens one

1. The image is built from the Containerfile. The first time takes a while; after that Podman's cache makes it quick, and a change you made to the Containerfile is in the very next start.
2. A container starts from it, with `--rm` (deleted when it stops), `no-new-privileges`, and limits from `config.py` (`SANDBOX_MEMORY`, `SANDBOX_CPUS`, `SANDBOX_PIDS`).
3. Its network is disconnected right away. Only you can switch it on: `/sandbox net on`.
4. It sees only these folders of your computer, all `noexec,nosuid,nodev`:

| On your computer | Inside | |
|---|---|---|
| `Shared Folder/Common` | `/workspace/Common` | always, read-write, shared by every running instance |
| `Shared Folder/Notebook_Engine` | `/workspace/Notebook_Engine` | always, **read-only** |
| `Shared Folder/<project>` | `/workspace/<project>` | at most one, mounted by the agent; no other instance can mount it meanwhile |

Nothing installed at runtime survives a stop. If the agent needs a package often, add it to the Containerfile.

## A new sandbox

Make a folder here with a `Containerfile` inside. Notebooks need `python3` in it; `sandbox_shell` needs `bash` and `timeout` (coreutils), which every Debian- or Ubuntu-based image has. The agent sees the new sandbox the next time it calls `check_sandbox`.

Editing a Containerfile leaves the old image behind on disk, without a name. `podman image prune` removes such leftovers (of all your images, not only these).
