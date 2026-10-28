# tools/sandbox/open_sandbox.py — build and start a sandbox for this instance. the logic is in classes/sandbox.py


def run(agent, name, projects=None):
    return agent.sandbox.open(name, projects or None)


TOOL = {
    "name": "open_sandbox",
    "description": "Build and start a sandbox, so sandbox_shell and the notebooks work. Pick it by what it is made of "
                   "(check_sandbox shows every Containerfile and its settings). One sandbox per instance: to switch, "
                   "close_sandbox first. Every start is clean, exactly as its Containerfile says, with the network OFF "
                   "(only the user can switch it on). /workspace/Common is always mounted and shared with every other "
                   "instance. Give every project the work needs here (several are fine, e.g. a project and Browser): "
                   "mounting one later restarts the sandbox. The first start of a sandbox builds its image, which can "
                   "take minutes.",
    "parameters": {"type": "object",
                   "properties": {"name": {"type": "string", "description": "the sandbox, e.g. python"},
                                  "projects": {"type": "array", "items": {"type": "string"},
                                               "description": "optional: existing project folders to mount, each at "
                                               "/workspace/<project> (check_projects lists them). the first one you "
                                               "can write in becomes the working folder"}},
                   "required": ["name"]},
}
