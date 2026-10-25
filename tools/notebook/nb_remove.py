# tools/notebook/nb_remove.py — remove a cell. see _notebook.py next to this file

from . import _notebook


def run(agent, path, cell_id):
    return _notebook.call(agent, "remove", path, cell_id=cell_id)


TOOL = {
    "name": "nb_remove",
    "description": "Remove one cell from an open notebook. Variables it created stay in the kernel until nb_rerun or "
                   "nb_close.",
    "parameters": {"type": "object",
                   "properties": {"path": {"type": "string"}, "cell_id": {"type": "string"}},
                   "required": ["path", "cell_id"]},
}
