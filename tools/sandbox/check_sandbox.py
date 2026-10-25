# tools/sandbox/check_sandbox.py — look at the sandboxes, change nothing. the logic is in classes/sandbox.py


def run(agent, name=None):
    return agent.sandbox.check(name)


TOOL = {
    "name": "check_sandbox",
    "description": "Look at the sandboxes without changing anything: each one's whole Containerfile (what is installed in "
                   "it, so what it is good for), whether its image is built, and which one runs in this instance (at most "
                   "one). Call it to pick the right sandbox before open_sandbox, and to see whether one runs already.",
    "parameters": {"type": "object",
                   "properties": {"name": {"type": "string",
                                           "description": "optional: one sandbox. left out: all of them"}}},
}
