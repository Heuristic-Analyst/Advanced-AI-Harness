# client.py — the MESSENGER between the agent's notebook tools and the kernels. it runs INSIDE the sandbox.
# (taken unchanged from the original AI-Harness. the nb_* tools run it through tools/notebook/_notebook.py)
# every nb_* tool call is one run of:   python3 -B client.py <base64 command>
# it delivers that one command, prints the answer and quits. the kernels (kernel.py) are what stay alive.
#   create / open    start a kernel for a notebook (create also makes the .ipynb file)
#   close            stop that kernel: its variables are gone, the file stays
#   rerun            close + start a fresh kernel + run every cell from the top
#   anything else    (show, add, edit, run, remove) is handed to the notebook's running kernel
# starting and stopping a kernel happens one messenger at a time (only_one), so a notebook never gets two kernels.
# the command arrives as base64 (letters and digits only), so quotes, $ or backticks in the code can't confuse bash.

import base64
import contextlib
import fcntl
import glob
import json
import os
import signal
import subprocess
import sys
import time
from multiprocessing.connection import Client

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kernel import door, WORKSPACE                         # the same address rule as the kernel, from the file next to us

KERNEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kernel.py")
LOG = "/tmp/nb-kernels.log"                                # what a kernel prints when it breaks. never ends up in a notebook


def connect(address, wait=0):
    """reach the kernel behind this address within `wait` seconds. returns the connection, or None = not open"""
    give_up = time.time() + wait
    while True:
        try:
            return Client(address)
        except (FileNotFoundError, ConnectionRefusedError):
            if time.time() >= give_up:
                return None
            time.sleep(0.1)

@contextlib.contextmanager
def only_one(path):
    """one messenger at a time may start or stop the kernel of a notebook. without this, two calls opening the same
    notebook at the same moment (one reply with two calls, or two subagents) would start two kernels for it"""
    with open(door(path) + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)                   # wait here while another messenger starts or stops this kernel
        yield                                              # the lock ends when the file is closed

def open_notebooks():
    """the notebooks that have a running kernel right now, for the overview after open, create and close"""
    found = []
    for info in sorted(glob.glob("/tmp/nb-*.json")):
        try:
            with open(info) as f:
                kernel = json.load(f)
            with open("/proc/" + str(kernel["pid"]) + "/cmdline", "rb") as f:   # is that process really this kernel?
                alive = f.read().replace(b"\0", b" ").decode(errors="replace")    # (after a sandbox restart, an old
            if "kernel.py" in alive and kernel["notebook"] in alive:              # kernel's number can belong to any program)
                found.append(kernel["notebook"])
        except (OSError, ValueError, KeyError):            # a kernel that crashed left its file behind: not open
            pass
    return "open notebooks now: " + (", ".join(found) or "none")

def start(path):
    """start a kernel for this notebook and wait until it answers. returns the connection, or an error text"""
    os.makedirs(os.path.dirname(path), exist_ok=True)      # a notebook in a new subfolder (work/a.ipynb): create the folder
    log = open(LOG, "a")
    process = subprocess.Popen([sys.executable, "-B", KERNEL, path], cwd=os.path.dirname(path),   # the notebook's folder
                               stdin=subprocess.DEVNULL, stdout=log, stderr=log,                 # becomes the kernel's
                               start_new_session=True)     # own session: it lives on after this messenger quits
    give_up = time.time() + 15
    while time.time() < give_up:
        desk = connect(door(path))
        if desk:
            return desk
        if process.poll() is not None:                     # the kernel died while starting: say why
            break
        time.sleep(0.1)
    with open(LOG) as f:
        last = f.read()[-1500:]
    return "error: the kernel did not start. the end of its log (" + LOG + "):\n" + last

def ask(desk, command, path):
    """hand one command to a running kernel and return its answer. too slow: stop the cell. dead: say so"""
    desk.send(command)
    timeout = command.get("timeout", 300)
    try:
        if desk.poll(timeout):                             # the normal case: an answer in time
            return desk.recv()
    except EOFError:                                       # the kernel died while working (e.g. the cell used up all memory)
        return ("error: the notebook kernel crashed (most often: out of memory). ALL variables are gone and the notebook "
                "is closed. the cells are still in the file: nb_open it again, then nb_rerun or run what you need")
    info = door(path) + ".json"
    with open(info) as f:                                  # too slow: ctrl+c for the kernel. the cell stops, the variables stay
        pid = json.load(f)["pid"]
    os.kill(pid, signal.SIGINT)
    try:
        if desk.poll(15):
            return "(it ran longer than " + str(timeout) + " seconds and was stopped)\n" + desk.recv()
    except EOFError:
        pass
    os.kill(pid, signal.SIGKILL)                           # it ignored ctrl+c (stuck in C code): end it for good
    for leftover in (door(path), info):
        if os.path.exists(leftover):
            os.remove(leftover)
    return ("error: the kernel did not react to being stopped and was killed. ALL variables are gone and the notebook is "
            "closed. the cells are still in the file: nb_open it again")

def close(path):
    desk = connect(door(path))
    if desk:
        desk.send({"cmd": "close"})
        try:
            desk.recv()
        except EOFError:
            pass
        for _ in range(50):                                # wait until it is really gone, so a new kernel can take the address
            if not os.path.exists(door(path)):
                break
            time.sleep(0.1)


def prepare(what, name, path):
    """make sure the right kernel runs for this command. returns (the connection, text to put in front of the answer),
    or (None, the whole answer) when there is nothing more to do"""
    desk = connect(door(path))                             # None = no kernel runs for this notebook = it is not open

    if what == "create":
        if desk:
            return None, name + " is already open. use it, or nb_close it first"
        if os.path.exists(path):
            return None, name + " exists already. nb_open opens it, or pick another name"
        desk = start(path)                                 # the kernel creates the empty .ipynb file right away
        if isinstance(desk, str):
            return None, desk
        return desk, "created " + name + " and started its kernel (no variables yet)\n" + open_notebooks() + "\n\n"

    if what == "open":
        if desk:
            return desk, name + " was already open, its variables are kept\n" + open_notebooks() + "\n\n"
        if not os.path.exists(path):
            return None, "there is no notebook " + name + ". nb_create makes a new one"
        desk = start(path)
        if isinstance(desk, str):
            return None, desk
        return desk, ("opened " + name + " with a fresh kernel: no variables yet. outputs in the file are from earlier runs; "
                      "run the cells you need (or nb_rerun for all)\n" + open_notebooks() + "\n\n")

    if what == "close":
        if not desk:
            return None, name + " is not open\n" + open_notebooks()
        desk.close()
        close(path)
        return None, "closed " + name + ": its variables are gone, the file stays\n" + open_notebooks()

    if not desk:                                           # every other command needs a running kernel
        if os.path.exists(path):
            return None, name + " is not open (or its kernel stopped, e.g. the sandbox restarted). nb_open it first"
        return None, "there is no notebook " + name + ". nb_create makes a new one"

    if what == "rerun":                                    # fresh kernel, then every cell from the top
        desk.close()
        close(path)
        desk = start(path)
        if isinstance(desk, str):
            return None, desk
        return desk, "fresh kernel (all old variables gone), every code cell run from the top:\n"

    return desk, ""                                        # show, add, edit, run, remove: its kernel runs, go ahead


def main(payload):
    command = json.loads(base64.b64decode(payload))
    name = command["notebook"]                             # as the agent wrote it, e.g. analysis/sales.ipynb
    path = os.path.normpath(os.path.join(WORKSPACE, name))
    with only_one(path):                                   # starting and stopping kernels: one messenger at a time
        desk, text = prepare(command["cmd"], name, path)
    if desk is None:                                       # nothing more to do: closed, not open, an error, ...
        return text
    work = {"create": "show", "open": "show", "rerun": "run_all"}.get(command["cmd"], command["cmd"])
    return text + ask(desk, dict(command, cmd=work), path)   # the real work, outside the lock: it may take minutes


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 -B client.py <base64 command>   (the nb_* tools call this, not you)")
    else:
        print(main(sys.argv[1]))
