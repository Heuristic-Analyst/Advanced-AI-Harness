# tools/notebook/nb_add.py — add a cell, optionally run it. see _notebook.py next to this file

from . import _notebook


def run(agent, path, source, kind="code", after=None, run=False):
    return _notebook.call(agent, "add", path, source=source, kind=kind, after=after, run=bool(run))


TOOL = {
    "name": "nb_add",
    "description": "Add a cell to an open notebook: at the end, or after a given cell. Set run to true to run it right away "
                   "(code cells). Returns the new cell's id, its output if it ran, and the overview of all cells.",
    "parameters": {"type": "object",
                   "properties": {"path": {"type": "string"},
                                  "source": {"type": "string", "description": "the code or markdown of the cell"},
                                  "kind": {"type": "string", "enum": ["code", "markdown"], "description": "default code"},
                                  "after": {"type": "string", "description": "the id of the cell to put it after. left "
                                            "out: at the end"},
                                  "run": {"type": "boolean", "description": "run it right away. default false"}},
                   "required": ["path", "source"]},
}
