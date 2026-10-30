# tools/sandbox/close_sandbox.py — stop this instance's sandbox. the logic is in classes/sandbox.py


def run(agent):
    return agent.sandbox.close()


TOOL = {
    "name": "close_sandbox",
    "description": "Stop this instance's sandbox. Everything installed or started inside is gone, open notebooks and "
                   "terminals are closed; the files in /workspace/Common and in the mounted projects stay, and the projects are free "
                   "for other instances again. Needed before open_sandbox can start a different one. When the user exits, "
                   "the sandbox is stopped anyway.",
    "parameters": {"type": "object", "properties": {}},
}
