# tools/sandbox/open_sandbox.py — build and start a sandbox for this instance. the logic is in classes/sandbox.py


def run(agent, name, project=None):
    return agent.sandbox.open(name, project or None)


TOOL = {
    "name": "open_sandbox",
    "description": "Build and start a sandbox, so sandbox_shell and the notebooks work. Pick it by what it is made of "
                   "(check_sandbox shows every Containerfile). One sandbox per instance: to switch, close_sandbox first. "
                   "Every start is clean, exactly as its Containerfile says, with the network OFF (only the user can "
                   "switch it on). /workspace/Common is always mounted and shared with every other instance. If the work "
                   "belongs to a project, give it here: mounting it later restarts the sandbox. The first start of a "
                   "sandbox builds its image, which can take minutes.",
    "parameters": {"type": "object",
                   "properties": {"name": {"type": "string", "description": "the sandbox, e.g. python"},
                                  "project": {"type": "string", "description": "optional: an existing project folder to "
                                              "mount at /workspace/<project> (check_projects lists them)"}},
                   "required": ["name"]},
}
