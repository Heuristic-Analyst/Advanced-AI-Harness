# Sandboxes

A sandbox is a throwaway Linux container ([Podman](https://podman.io)) where the agent runs everything: commands, installs, notebooks. It never runs anything on your computer itself.

| Sandbox | What it is |
|---|---|
| `python` | Python 3.12 with numpy, pandas and matplotlib. The one notebooks need. |
| `ubuntu` | Plain Ubuntu 24.04. No Python. |
| `ai-lab` | PyTorch with CUDA, transformers and friends. Gets your NVIDIA GPU (`sandbox.json`). |
| `browser` | Chromium for the agent, with a screen you can watch. Works with the `Browser` project (`Shared Folder/Browser`). |

## How a sandbox looks

One folder per sandbox, with a file always called `Containerfile`, and optionally its settings, `sandbox.json`:

```
Sandboxes/
└── python/
    ├── Containerfile
    └── sandbox.json        optional
```

```dockerfile
FROM docker.io/library/python:3.12-slim
RUN pip install --no-cache-dir numpy pandas matplotlib
```

The folder's name is the sandbox's name: lowercase letters, digits and `-` only (Podman's rule for image names). The agent reads the Containerfiles (`check_sandbox`) to pick the sandbox that fits a task.

## sandbox.json: a sandbox's settings

Most sandboxes need none: then the defaults in `config.py` apply (2 GB memory, 2 CPU cores, no GPU). A sandbox that needs more gets a `sandbox.json` next to its Containerfile. **You** write it; the agent can read it (`check_sandbox`) but never change it: this folder is never mounted into a sandbox, and no tool writes here.

```json
{
  "_about": "anything starting with _ is a note for you, and is skipped",
  "memory": "8g",
  "cpus": 4,
  "gpu": true,
  "view": 6080
}
```

| Setting | What it does | Left out |
|---|---|---|
| `memory` | How much memory it may use, like `"4g"` or `"512m"`. | `SANDBOX_MEMORY` (2g) |
| `cpus` | How many CPU cores it may use. Not more than your computer has, or it won't start. | `SANDBOX_CPUS` (2) |
| `gpu` | `true`: it gets your NVIDIA GPUs. Needs a one-time setup, below. | no GPU |
| `view` | A port inside the sandbox that you can open in your own browser. `/sandbox` shows the link, e.g. `http://127.0.0.1:53817`. | nothing to open |

Only these four exist. Anything else (a typo too) makes the sandbox unusable until it is fixed, and `check_sandbox` and `/sandbox` say what is wrong, so nothing you didn't mean can reach Podman.

**About `view`.** It only ever opens on your own computer (127.0.0.1), on a free port that stays the same until you close the program. It doesn't use the network: every connection is carried by `podman exec` (`classes/relay.py`), so it works with the sandbox's network off, on Linux, Mac and Windows alike. It needs `python3` in the sandbox. The program inside should listen on its own 127.0.0.1, then nothing else can reach it at all.

## The GPU (`"gpu": true`)

The sandbox gets every NVIDIA GPU, the same way on every system: `--device nvidia.com/gpu=all` (CDI). Podman can only do that once the NVIDIA Container Toolkit is set up, once per computer:

- **Linux:** install the NVIDIA driver and the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html). Then check `nvidia-ctk cdi list` shows your GPUs; if not, `sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`. Fedora and other SELinux systems also need `sudo setsebool -P container_use_devices=true`.
- **Windows:** install the NVIDIA driver on Windows (nothing else there). The toolkit goes into Podman's machine: `podman machine ssh`, install the toolkit in there, then `nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`.
- **Mac:** no NVIDIA GPUs exist there. Set `"gpu": false`.

Test it once by hand: `podman run --rm --device nvidia.com/gpu=all ubuntu nvidia-smi -L` must list your GPUs. If the toolkit is missing, opening the sandbox fails with a message that says so.

## What happens when the agent opens one

1. The image is built from the Containerfile. The first time takes a while; after that Podman's cache makes it quick, and a change you made to the Containerfile is in the very next start.
2. A container starts from it, with `--rm` (deleted when it stops), `no-new-privileges`, and limits: memory and cpus from its `sandbox.json` or `config.py`, and `SANDBOX_PIDS`. Its `/dev/shm` (shared memory, which browsers and PyTorch use) is as big as its memory.
3. Its network is disconnected right away. Only you can switch it on: `/sandbox net on`.
4. It sees only these folders of your computer, all `noexec,nosuid,nodev`:

| On your computer | Inside | |
|---|---|---|
| `Shared Folder/Common` | `/workspace/Common` | always, read-write, shared by every running instance |
| `Shared Folder/Notebook_Engine` | `/workspace/Notebook_Engine` | always, **read-only** |
| `Shared Folder/<project>` | `/workspace/<project>` | as many as the agent mounts; no other instance can mount one meanwhile |
| a read-only project, e.g. `Shared Folder/Browser` | `/workspace/Browser` | **read-only**, except the subfolders named in `READONLY_PROJECTS` (`config.py`), e.g. `Browser/tmp` |

Nothing installed at runtime survives a stop. If the agent needs a package often, add it to the Containerfile.

## A new sandbox

Make a folder here with a `Containerfile` inside. Notebooks need `python3` in it; `sandbox_shell` needs `bash` and `timeout` (coreutils), which every Debian- or Ubuntu-based image has. The agent sees the new sandbox the next time it calls `check_sandbox`.

Editing a Containerfile leaves the old image behind on disk, without a name. `podman image prune` removes such leftovers (of all your images, not only these).
