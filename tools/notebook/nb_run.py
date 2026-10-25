# tools/notebook/nb_run.py — run cells, in the order given. see _notebook.py next to this file

from . import _notebook


def run(agent, path, cell_ids):
    if isinstance(cell_ids, str):                      # one id given as text instead of a list: fine too
        cell_ids = [cell_ids]
    return _notebook.call(agent, "run", path, cell_ids=cell_ids)


TOOL = {
    "name": "nb_run",
    "description": "Run cells of an open notebook, in the order given, and get their output: printed text, the value of a "
                   "bare last line (like Jupyter), errors with the line that failed, plots (saved in the notebook; you get "
                   "a note). Several cells stop at the first error. A run that takes too long is stopped; the variables "
                   "are kept.",
    "parameters": {"type": "object",
                   "properties": {"path": {"type": "string"},
                                  "cell_ids": {"type": "array", "items": {"type": "string"},
                                               "description": "one or more cell ids, run in this order"}},
                   "required": ["path", "cell_ids"]},
}
