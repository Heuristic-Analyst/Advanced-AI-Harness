# tools/notebook/nb_show.py — the whole open notebook. see _notebook.py next to this file

from . import _notebook


def run(agent, path):
    return _notebook.call(agent, "show", path)


TOOL = {
    "name": "nb_show",
    "description": "Show a whole open notebook: every cell with its id, state, full code and output. Use it when you are "
                   "unsure what is in it; the overview after every other notebook call is usually enough.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
}
