# tools/sandbox/sandbox_shell.py — run a bash command INSIDE the sandbox, never on the user's computer.
# the logic is in classes/sandbox.py (exec). a long answer is saved as a result, like every tool's (functions/results.py)

from config import COMMAND_TIMEOUT


def run(agent, command):
    return agent.sandbox.exec(command)


TOOL = {
    "name": "sandbox_shell",
    "description": "Run a bash command inside this instance's sandbox (a Linux container, you are root in it) and get what "
                   "it printed. It starts in the first mounted project you can write in, or in /workspace/Common. "
                   "Only /workspace/Common and the mounted projects (/workspace/<project>) are kept; everything else inside is yours to install "
                   "and build in, and gone when the sandbox stops. Files in /workspace can't be executed directly: run "
                   "them with an interpreter (python x.py, bash x.sh). A command still running after "
                   + str(COMMAND_TIMEOUT) + " seconds is stopped: start longer jobs in the background with their output "
                   "in a file (nohup python job.py > job.log 2>&1 &) and check the file later. Several calls in one reply "
                   "run at the same time.",
    "parameters": {"type": "object",
                   "properties": {"command": {"type": "string", "description": "the bash command, e.g. ls -la"}},
                   "required": ["command"]},
}
