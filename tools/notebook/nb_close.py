# tools/notebook/nb_close.py — stop a notebook's kernel. see _notebook.py next to this file

from . import _notebook


def run(agent, path):
    return _notebook.call(agent, "close", path)


TOOL = {
    "name": "nb_close",
    "description": "Close a notebook: its kernel stops and its variables are gone; the file with all cells and outputs "
                   "stays. Close notebooks you are done with: each open one uses memory in the sandbox, and another "
                   "instance can't open it while it is open here.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
}
