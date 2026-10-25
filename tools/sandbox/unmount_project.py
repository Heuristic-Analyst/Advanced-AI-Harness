# tools/sandbox/unmount_project.py — unmount the project. the logic is in classes/sandbox.py


def run(agent):
    return agent.sandbox.unmount()


TOOL = {
    "name": "unmount_project",
    "description": "Unmount the project from this instance's sandbox, so other instances can mount it. Its files stay in "
                   "the user's Shared Folder. /workspace/Common stays mounted. This RESTARTS the sandbox: whatever was "
                   "installed or started inside is gone, open notebooks are closed.",
    "parameters": {"type": "object", "properties": {}},
}
