# tools/results/read_result.py — shows ONE part of a saved result (functions/results.py), never more.
# so a huge result can be read without filling the context: one part now, the next part only if it is needed.

from functions import results


def run(agent, name, part=1):
    parts = results.load(agent.results_dir, name)    # only this conversation's results folder
    if parts is None:
        return results.not_found(agent.results_dir, name)
    part = int(part)                                 # the model may send "2" as text: make it a number
    count = len(parts)
    if str(part) not in parts:                       # the keys in the file are text: "1", "2", ...
        return name + " has " + str(count) + " part(s): part must be a number from 1 to " + str(count)
    head = "[" + name + ": part " + str(part) + " of " + str(count)
    if part < count:
        head += ". the next one: read_result(" + name + ", " + str(part + 1) + ")]"
    else:
        head += ", the last part]"
    return head + "\n" + parts[str(part)]


TOOL = {
    "name": "read_result",
    "description": "Read one part of a saved result. Tool results too long for your context are saved in parts "
                   "(results-1, results-2, ...), and you only saw their start and end. This shows one whole part. "
                   "Read only the parts you need; to find the right part first, use search_result.",
    "parameters": {"type": "object",
                   "properties": {"name": {"type": "string", "description": "the result's name, e.g. results-3"},
                                  "part": {"type": "integer", "description": "which part, from 1. default 1"}},
                   "required": ["name"]},
}
