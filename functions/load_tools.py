import os
import importlib.util


def load_tools(folder):
    """find every tool in folder, also in subfolders, and load it. returns a dict:
        tool name -> {"schema": what the model sees, in the format it wants,  "run": the function to call}
    files and folders starting with _ are skipped: room for helper code next to the tools (_helpers.py).
    a new tool = a new file: nothing else has to change anywhere"""
    tools = {}
    found_in = {}                                                 # tool name -> its file, to name both on a clash
    for current, subfolders, files in os.walk(folder):            # the folder, then every folder inside it
        subfolders[:] = sorted(s for s in subfolders if not s.startswith((".", "_")))   # skip __pycache__, _drafts
        for file in sorted(files):
            if not file.endswith(".py") or file.startswith("_"):  # not python, or a helper: not a tool
                continue
            path = os.path.join(current, file)
            where = os.path.relpath(path, os.path.dirname(folder))   # e.g. tools/calculate.py
            spec = importlib.util.spec_from_file_location(where[:-3].replace(os.sep, "."), path)   # load it by its
            module = importlib.util.module_from_spec(spec)                                          # path: no import
            spec.loader.exec_module(module)                                                         # line needed
            if not hasattr(module, "TOOL") or not hasattr(module, "run"):
                raise SystemExit(where + " is not a tool: it needs TOOL and run. (a helper? start its name with _)")
            name = module.TOOL["name"]
            if name in tools:                                     # two files with the same tool name
                raise SystemExit("two tools are called '" + name + "': " + found_in[name] + " and " + where
                                 + ". rename one")
            tools[name] = {"schema": {"type": "function", "function": module.TOOL},   # how the model wants it
                           "run": module.run}
            found_in[name] = where
    return tools
