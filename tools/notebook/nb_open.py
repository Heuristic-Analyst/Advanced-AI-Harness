# tools/notebook/nb_open.py — open an existing notebook and show all of it. see _notebook.py next to this file

from . import _notebook


def run(agent, path):
    return _notebook.call(agent, "open", path)


TOOL = {
    "name": "nb_open",
    "description": "Open an existing notebook (.ipynb) in Common/ or the mounted project and get all of it: every cell "
                   "with id, state, code and output. Opening starts a fresh kernel with no variables: outputs in the file "
                   "are from earlier runs, so run the cells you need (or nb_rerun for all). Already open? Its variables "
                   "are kept and you just get the view. Needed again after the sandbox restarted (mount_project and "
                   "unmount_project restart it), because that stops every kernel.",
    "parameters": {"type": "object",
                   "properties": {"path": {"type": "string", "description": "e.g. Common/analysis.ipynb"}},
                   "required": ["path"]},
}
