# tools/notebook/_notebook.py — what every nb_* tool next to it goes through. (the _ in front: not a tool, the loader
# skips it)
# the notebooks run INSIDE the sandbox, never on your computer. their engine is in Shared Folder/Notebook_Engine
# (kernel.py and client.py, from the original AI-Harness), which every sandbox sees read-only at
# /workspace/Notebook_Engine. one tool call = one run of client.py inside the sandbox, with one command; client.py
# starts, stops or asks the notebook's kernel, a program that stays alive and keeps the notebook's variables.
# the notebooks themselves are .ipynb files in the folders that are kept: Common/... or <project>/...
# an open notebook is locked (classes/sandbox.py, claim_notebook): another running instance can't open it at the same
# time, because its kernel would run in another container and save over this one's work.

import json
import base64


def resolve(sandbox, path):
    """the notebook's path as the engine needs it, e.g. "Common/sales.ipynb", and None. or None and what is wrong.
    the first folder may be written in any spelling (common/ for Common/), but must be Common or a mounted project the
    agent can write in (not a read-only one)"""
    text = str(path).replace("\\", "/").strip()
    if text.startswith("/workspace/"):                 # "/workspace/Common/x.ipynb" means Common/x.ipynb
        text = text[len("/workspace/"):]
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if text.startswith("/") or ".." in parts or len(parts) < 2 or not parts[-1].endswith(".ipynb") \
            or parts[-1] == ".ipynb":
        return None, ("the notebook must be a path ending in .ipynb inside " + allowed(sandbox)
                      + ", e.g. " + sandbox.common + "/analysis.ipynb, with no .. in it")
    folders = {sandbox.common.lower(): sandbox.common}
    for project in sandbox.writable_projects():
        folders[project.lower()] = project
    real = folders.get(parts[0].lower())
    if not real:                                       # anywhere else it would be gone when the sandbox stops, and
        return None, "a notebook must be inside " + allowed(sandbox)   # Notebook_Engine is read-only
    parts[0] = real
    return "/".join(parts), None


def allowed(sandbox):
    text = sandbox.common + "/..."
    for project in sandbox.writable_projects():
        text += " or " + project + "/... (a mounted project)"
    return text


def call(agent, cmd, path, **args):
    """send one command for one notebook to the engine in the sandbox. returns the answer as text"""
    sandbox = agent.sandbox
    if not sandbox.engine_ready():                     # checked on your computer, before the sandbox
        return ("the notebook engine is missing: there is no Shared Folder/" + sandbox.engine + "/client.py. "
                "tell the user, notebooks don't work without it")
    if not sandbox.running():
        return sandbox.not_running()
    notebook, problem = resolve(sandbox, path)
    if problem:
        return problem
    had_it = notebook in sandbox.notebooks             # open in this instance already
    if cmd in ("create", "open") and not had_it and not sandbox.claim_notebook(notebook):
        return (notebook + " is open in another running instance. use another notebook, or try again when it is "
                "closed there")
    answer = send(sandbox, cmd, notebook, args)
    opened = answer.startswith(("created ", "opened ", notebook + " was already open"))
    if cmd in ("create", "open") and not opened and not had_it:
        sandbox.free_notebook(notebook)                # it didn't open (no such file, no python3, ...): lock off again
    if cmd == "close" or "the notebook is closed" in answer or answer.startswith(notebook + " is not open"):
        sandbox.free_notebook(notebook)                # closed, or its kernel died (e.g. out of memory)
    return answer


def send(sandbox, cmd, notebook, args):
    """run client.py in the sandbox with one command. the command goes as base64 (letters and digits only), so quotes,
    $ or backticks in the code can't confuse bash"""
    command = dict(args, cmd=cmd, notebook=notebook,
                   timeout=max(30, sandbox.timeout - 30))   # a slow cell is stopped before the command's own limit
    payload = base64.b64encode(json.dumps(command).encode()).decode()
    answer = sandbox.exec("python3 -B /workspace/" + sandbox.engine + "/client.py " + payload)   # -B: no __pycache__,
    if "python3: command not found" in answer or answer.startswith("(exit code 127"):          # the engine is read-only
        return ("this sandbox has no python3, so notebooks don't work in it. close it and open one that has python3 "
                "(check_sandbox shows them, e.g. python)")
    return answer
