# kernel.py — the notebook KERNEL. it runs INSIDE the sandbox, never on your machine.
# (taken unchanged from the original AI-Harness. it lives in Shared Folder/Notebook_Engine, which every sandbox sees
#  read-only at /workspace/Notebook_Engine, so the agent can use it but never change it.)
# one kernel = one open notebook. client.py starts it with:   python3 -B kernel.py <notebook.ipynb>
# then it keeps running and waits for commands from client.py. it holds two things:
#   - the variables: everything the cells create (that is what a jupyter "kernel" is)
#   - the cells: their code, their outputs, and whether they ran in this kernel
# after every change it writes the whole notebook into the .ipynb file, so the user can open it any time.
# it stops when client.py sends "close" (nb_close, nb_rerun) or when the sandbox stops.
# only the python standard library is used, so it works in any sandbox that has python3.

import ast
import base64
import hashlib
import io
import json
import os
import signal
import sys
import tempfile
import traceback
import uuid
from multiprocessing.connection import Listener

WORKSPACE = os.environ.get("NB_WORKSPACE", "/workspace")   # the shared folder. notebook paths are shown relative to it
SHOW_OUTPUT = 4000                                         # characters of one output the agent sees. the file keeps all of it


def door(path):
    """the address of the kernel of one notebook: a socket file in /tmp. client.py finds the kernel through it"""
    return "/tmp/nb-" + hashlib.md5(path.encode()).hexdigest()[:10]

def new_id():
    return uuid.uuid4().hex[:8]                            # e.g. "3f9a1c0b". stays the same when cells move around

def cut(text, limit=SHOW_OUTPUT):
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...(" + str(len(text) - limit) + " more characters, all of it is in the notebook file)"

def joined(text):
    """the file format allows text both ways: "a\\nb" or ["a\\n", "b"] (jupyter saves lists). always give back the first"""
    return "".join(text) if isinstance(text, list) else (text or "")


# ======================================================================================================================
# running one cell: like exec(), plus everything a notebook needs around it
# ======================================================================================================================

running = False                                            # True only while a cell runs: then ctrl+c stops the cell

def on_interrupt(signum, frame):
    if running:                                            # a cell runs too long: client.py sends ctrl+c. stop the cell,
        raise KeyboardInterrupt                            # the kernel and its variables live on
                                                           # between cells: ignore it, nothing to stop

def execute(source, memory, cell_id, count):
    """run source with memory as its variables. returns the outputs in .ipynb format"""
    global running
    name = "<cell " + cell_id + ">"                        # tracebacks then say which cell and which line
    result = error = None
    with tempfile.TemporaryFile() as caught:
        sys.stdout.flush()
        sys.stderr.flush()
        saved = os.dup(1), os.dup(2)
        os.dup2(caught.fileno(), 1)                        # catch everything the cell prints: print(), errors, and even
        os.dup2(caught.fileno(), 2)                        # programs it starts (os.system, subprocess)
        running = True
        try:
            tree = ast.parse(source, name)
            last = None
            if tree.body and isinstance(tree.body[-1], ast.Expr):   # like jupyter: a bare last line is shown (df.head())
                last = ast.Expression(tree.body.pop().value)
            exec(compile(tree, name, "exec"), memory)
            if last is not None:
                result = eval(compile(last, name, "eval"), memory)
        except KeyboardInterrupt:
            error = {"output_type": "error", "ename": "KeyboardInterrupt",
                     "evalue": "stopped because it took too long. the variables are kept", "traceback": []}
        except BaseException as e:                         # BaseException: exit() in a cell must not end the kernel
            tb = e.__traceback__
            while tb and tb.tb_frame.f_code.co_filename != name:   # skip the kernel's own lines, start at the cell
                tb = tb.tb_next
            error = {"output_type": "error", "ename": type(e).__name__, "evalue": str(e),
                     "traceback": traceback.format_exception(type(e), e, tb)}
        finally:
            running = False
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            os.close(saved[0])
            os.close(saved[1])
        figures = take_figures()
        caught.seek(0)
        printed = caught.read().decode(errors="replace")

    outputs = []
    if printed:
        outputs.append({"output_type": "stream", "name": "stdout", "text": printed})
    for png in figures:
        outputs.append({"output_type": "display_data", "data": {"image/png": png, "text/plain": "<Figure>"}, "metadata": {}})
    if error:
        outputs.append(error)
    elif result is not None:
        data = {"text/plain": repr(result)}
        html = getattr(result, "_repr_html_", None)        # pandas tables look like tables in the notebook
        if callable(html):
            try:
                data["text/html"] = html()
            except Exception:
                pass
        outputs.append({"output_type": "execute_result", "execution_count": count, "data": data, "metadata": {}})
    return outputs

def take_figures():
    """matplotlib plots the cell made: as png (base64), then closed. no matplotlib used? nothing to do"""
    plt = sys.modules.get("matplotlib.pyplot")
    if not plt:
        return []
    pngs = []
    try:
        for number in plt.get_fignums():
            buffer = io.BytesIO()
            plt.figure(number).savefig(buffer, format="png", bbox_inches="tight")
            pngs.append(base64.b64encode(buffer.getvalue()).decode())
        plt.close("all")
    except Exception:
        pass
    return pngs

def as_text(outputs):
    """the outputs of a cell, as the agent reads them"""
    parts = []
    for o in outputs:
        kind = o.get("output_type")
        data = o.get("data", {})
        if kind == "stream":
            parts.append(joined(o.get("text")).rstrip("\n"))
        elif kind in ("display_data", "execute_result"):
            if "image/png" in data:
                parts.append("[figure: a plot, shown in the notebook]")
            elif "text/plain" in data:
                parts.append(joined(data["text/plain"]))
            else:
                parts.append("[" + (", ".join(data) or "empty") + " output, shown in the notebook]")
        elif kind == "error":
            parts.append(joined(o.get("traceback")).rstrip("\n") or (o.get("ename", "") + ": " + o.get("evalue", "")))
    return cut("\n".join(parts)) if parts else "(no output)"


# ======================================================================================================================
# the notebook: the cells, the variables, and the .ipynb file
# ======================================================================================================================

class Notebook:
    def __init__(self, path):
        self.path = path
        self.memory = {"__name__": "__main__"}             # every variable lives in here, as long as the kernel runs
        self.count = 0                                     # the [n] in front of a cell: how many runs so far
        self.cells = []                                    # {id, type, source, outputs, count, ran, metadata, attachments}
        self.metadata = {"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                         "language_info": {"name": "python"}}   # the notebook's own settings. an opened notebook keeps its own
        self.saved_at = None                               # when we last wrote the file. a different time = someone else did
        if not os.path.exists(path):
            self.save()                                    # a new notebook: create the file right away
        else:
            try:
                self.load()
            except ValueError:                             # unreadable (half saved?): start empty, but NEVER save over it.
                pass                                       # saved_at stays None, so every command tries to read it again first

    # --- the file ---
    def load(self):
        """read the .ipynb file. cells that already ran in this kernel keep that knowledge"""
        try:
            with open(self.path, encoding="utf-8") as f:
                notebook = json.load(f)
        except ValueError as e:                            # not valid json: nothing here is changed, the old cells stay
            raise ValueError("the notebook file can't be read right now (maybe it is being saved, or it is broken: "
                             + str(e) + "). nothing was changed. try again in a moment, or ask the user to fix the file")
        known = {c["id"]: c for c in self.cells}
        self.cells = []
        for c in notebook.get("cells", []):
            outputs = c.get("outputs", [])
            for o in outputs:                              # jupyter saves text as lists of lines. we work with plain text
                if "text" in o:
                    o["text"] = joined(o["text"])
                for kind, value in o.get("data", {}).items():
                    if isinstance(value, list):
                        o["data"][kind] = joined(value)
            cell = {"id": c.get("id") or new_id(), "type": c.get("cell_type", "code"), "source": joined(c.get("source")),
                    "outputs": outputs, "count": c.get("execution_count"), "ran": None,
                    "metadata": c.get("metadata", {}), "attachments": c.get("attachments")}   # kept as they were
            if cell["id"] in known:
                cell["ran"] = known[cell["id"]]["ran"]
            self.cells.append(cell)
        self.metadata = notebook.get("metadata", self.metadata)
        self.saved_at = os.path.getmtime(self.path)

    def save(self):
        """write the whole notebook. first to a temporary file, then swapped in, so no one ever sees half a file"""
        cells = []
        for c in self.cells:
            cell = {"cell_type": c["type"], "id": c["id"], "metadata": c.get("metadata", {}), "source": c["source"]}
            if c.get("attachments"):                       # images pasted into a markdown cell
                cell["attachments"] = c["attachments"]
            if c["type"] == "code":
                cell["execution_count"] = c["count"]
                cell["outputs"] = c["outputs"]
            cells.append(cell)
        notebook = {"cells": cells, "nbformat": 4, "nbformat_minor": 5, "metadata": self.metadata}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        temporary = self.path + ".saving"
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)
        os.replace(temporary, self.path)
        self.saved_at = os.path.getmtime(self.path)

    def changed_outside(self):
        """did someone else (the user, in their editor) change the file since we wrote it? then read it again"""
        if os.path.exists(self.path) and os.path.getmtime(self.path) != self.saved_at:
            self.load()
            return "note: the notebook file was changed outside (probably by the user) and was read again.\n\n"
        return ""

    # --- what the agent sees ---
    def status(self, c):
        if c["type"] != "code":
            return c["type"]                               # markdown (or raw)
        if c["ran"] is None:
            return "not run" if c["count"] is None else "old output, not run in this kernel"
        text = "ran [" + str(c["count"]) + "]"
        if c["ran"] != c["source"]:
            text += ", EDITED since, output is stale"
        if any(o.get("output_type") == "error" for o in c["outputs"]):
            text += ", error"
        return text

    def outline(self):
        """one line per cell: where the agent is. it comes with every answer"""
        lines = [os.path.relpath(self.path, WORKSPACE) + ": " + str(len(self.cells)) + " cells"]
        for number, c in enumerate(self.cells, 1):
            first = (c["source"].strip().splitlines() or [""])[0]
            first = first[:60] + ("..." if len(first) > 60 else "")
            lines.append("  " + str(number) + ". " + c["id"] + "  " + self.status(c) + "  | " + first)
        return "\n".join(lines)

    def full(self):
        """every cell with its whole source and its output"""
        parts = [self.outline()]
        for number, c in enumerate(self.cells, 1):
            parts.append("\n--- " + str(number) + ". " + c["id"] + " (" + self.status(c) + ") ---\n" + (c["source"] or "(empty)"))
            if c["type"] == "code" and c["outputs"]:
                parts.append(">>> output:\n" + as_text(c["outputs"]))
        return "\n".join(parts)

    # --- the commands ---
    def find(self, cell_id):
        for position, c in enumerate(self.cells):
            if c["id"] == cell_id:
                return position, c
        raise LookupError("no cell '" + str(cell_id) + "'. the cells are:\n" + self.outline())

    def run_cell(self, cell_id):
        position, c = self.find(cell_id)
        if c["type"] != "code":
            return "(" + c["type"] + " cell, nothing to run)"
        self.count += 1
        source = c["source"]
        outputs = execute(source, self.memory, cell_id, self.count)
        note = self.changed_outside()                      # the user saved the file while the cell ran? read their version
        try:                                               # first, so saving the outputs below doesn't overwrite it
            position, c = self.find(cell_id)
        except LookupError:
            return note + as_text(outputs) + "\n(this cell was deleted outside while it ran, so its output is not saved)"
        c["outputs"] = outputs
        c["count"] = self.count
        c["ran"] = source                                  # what really ran. edited meanwhile? then the overview says EDITED
        self.save()                                        # outputs go into the file right after every run
        return note + as_text(outputs)

    def run_many(self, cell_ids):
        """run cells in this order, stop at the first error"""
        answers = []
        for cell_id in cell_ids:
            try:
                answer = self.run_cell(cell_id)
            except LookupError:
                answers.append("--- " + cell_id + " ---\n(no such cell, skipped)")
                continue
            answers.append("--- " + cell_id + " ---\n" + answer)
            if any(o.get("output_type") == "error" for o in self.find(cell_id)[1]["outputs"]):
                answers.append("(stopped at this error)")
                break
        return "\n".join(answers or ["(no code cells to run)"])

    def handle(self, command):
        note = self.changed_outside()
        what = command["cmd"]

        if what == "show":
            return note + self.full()

        if what == "add":
            kind = command.get("kind") or "code"
            if kind not in ("code", "markdown"):
                return "kind must be code or markdown"
            cell = {"id": new_id(), "type": kind, "source": command.get("source", ""), "outputs": [], "count": None,
                    "ran": None, "metadata": {}}
            after = command.get("after")
            position = self.find(after)[0] + 1 if after else len(self.cells)   # no "after": at the end
            self.cells.insert(position, cell)
            self.save()
            answer = "added cell " + cell["id"]
            if command.get("run"):
                answer += "\n>>> output:\n" + self.run_cell(cell["id"])
            return note + answer + "\n\n" + self.outline()

        if what == "edit":
            position, cell = self.find(command["cell_id"])
            cell["source"] = command.get("source", "")
            self.save()
            answer = "edited cell " + cell["id"]
            if command.get("run"):
                answer += "\n>>> output:\n" + self.run_cell(cell["id"])
            return note + answer + "\n\n" + self.outline()

        if what == "remove":
            position, cell = self.find(command["cell_id"])
            del self.cells[position]
            self.save()
            return note + "removed cell " + cell["id"] + " (variables it made stay until the kernel restarts)\n\n" + self.outline()

        if what == "run":
            cell_ids = command.get("cell_ids") or []
            if len(cell_ids) == 1:
                return note + self.run_cell(cell_ids[0]) + "\n\n" + self.outline()
            return note + self.run_many(cell_ids) + "\n\n" + self.outline()

        if what == "run_all":                              # every code cell, top to bottom (nb_rerun, on a fresh kernel)
            return note + self.run_many([c["id"] for c in self.cells if c["type"] == "code"]) + "\n\n" + self.outline()

        return "unknown command '" + what + "'"


# ======================================================================================================================
# the kernel's life: wait for commands, forever
# ======================================================================================================================

def serve(path):
    os.environ.setdefault("MPLBACKEND", "Agg")             # plots are drawn into memory, not into a window
    nothing = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nothing, 0)                                    # a cell calling input() gets "end of input" instead of hanging
    sys.stdin = open(os.devnull)
    signal.signal(signal.SIGINT, on_interrupt)
    notebook = Notebook(path)
    address = door(path)
    if os.path.exists(address):                            # left over from a kernel that crashed
        os.remove(address)
    with open(address + ".json", "w") as f:                # who we are: client.py reads it to interrupt us and to list
        json.dump({"pid": os.getpid(), "notebook": os.path.relpath(path, WORKSPACE)}, f)   # the open notebooks
    with Listener(address) as desk:
        while True:                                        # wait forever: this loop is why the variables survive
            messenger = desk.accept()
            try:
                command = messenger.recv()
                if command["cmd"] == "close":
                    messenger.send("closed")
                    break
                try:
                    messenger.send(notebook.handle(command))
                except (LookupError, KeyError, ValueError) as e:   # a wrong cell id, a missing field, an unreadable file
                    messenger.send("error: " + str(e).strip("'\""))
                except Exception:                          # anything else: report it, but the kernel and its variables live on
                    messenger.send("error inside the notebook kernel (the variables are kept):\n" + traceback.format_exc())
            except (EOFError, OSError):                    # the messenger gave up and left: nothing to answer
                pass
            finally:
                messenger.close()
    os.remove(address + ".json")                           # the socket file itself is removed by the Listener


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 -B kernel.py <notebook.ipynb>   (normally started by client.py, not by hand)")
    else:
        serve(os.path.abspath(sys.argv[1]))
