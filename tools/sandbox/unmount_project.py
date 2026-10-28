# tools/sandbox/unmount_project.py — unmount one project. the logic is in classes/sandbox.py


def run(agent, name=None):
    return agent.sandbox.unmount(name or None)


TOOL = {
    "name": "unmount_project",
    "description": "Unmount one project from this instance's sandbox, so other instances can mount it. Its files stay in "
                   "the user's Shared Folder; the other projects and /workspace/Common stay mounted. This RESTARTS the "
                   "sandbox: whatever was installed or started inside is gone, open notebooks are closed.",
    "parameters": {"type": "object",
                   "properties": {"name": {"type": "string", "description": "the project to unmount. may be left out "
                                           "when only one is mounted"}}},
}
