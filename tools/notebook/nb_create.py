# tools/notebook/nb_create.py — a new notebook, and its kernel started. see _notebook.py next to this file

from . import _notebook


def run(agent, path):
    return _notebook.call(agent, "create", path)


TOOL = {
    "name": "nb_create",
    "description": "Create a new Jupyter notebook (.ipynb) in Common/ or in the mounted project, and open it: its kernel "
                   "starts in the sandbox and keeps every variable between runs, like Jupyter. Every change is saved to "
                   "the file at once, so the user can open it any time. Every notebook answer ends with an overview of "
                   "all cells: id, state (ran [n], not run, EDITED since = output is stale, error) and first line: read "
                   "it to know where you are. Load the notebook skill before you start working in notebooks.",
    "parameters": {"type": "object",
                   "properties": {"path": {"type": "string", "description": "Common/ or the mounted project, then the "
                                           "file, e.g. Common/analysis.ipynb or website/stats/report.ipynb (missing "
                                           "folders are created)"}},
                   "required": ["path"]},
}
