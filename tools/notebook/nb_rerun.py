# tools/notebook/nb_rerun.py — fresh kernel, then every cell from the top. see _notebook.py next to this file

from . import _notebook


def run(agent, path):
    return _notebook.call(agent, "rerun", path)


TOOL = {
    "name": "nb_rerun",
    "description": "Run the whole notebook from scratch: a fresh kernel (all variables gone), then every code cell from "
                   "the top, stopping at the first error. Use it to check that the notebook works top to bottom, or when "
                   "the variables got messy. The whole run must finish within the time limit; for very long notebooks, "
                   "run the cells in parts with nb_run.",
    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
}
