# tools/sandbox/terminal.py — run a command in a shell that STAYS OPEN inside the sandbox (unlike sandbox_shell, which
# opens a new one for every command). the logic is in classes/sandbox.py (terminal) and classes/terminal.py

from config import COMMAND_TIMEOUT


def run(agent, command, terminal=None):
    return agent.sandbox.terminal(command, terminal)


TOOL = {
    "name": "terminal",
    "description": "Run a bash command in a terminal inside the sandbox that STAYS OPEN between calls, like a terminal "
                   "window: where you cd'd to, exported variables, shell functions and an activated environment "
                   "(source .venv/bin/activate) are still there for the next call. sandbox_shell, in contrast, starts "
                   "fresh every time. The first call with a name opens that terminal in the working folder; up to 4 "
                   "can be open (e.g. main and server), and different terminals run at the same time, while calls to "
                   "the same one wait for each other. Every call answers with the folder the terminal is in now. "
                   "Commands get no keyboard input (stdin is empty): use flags like -y, or write the input to a file. "
                   "A command still running after " + str(COMMAND_TIMEOUT) + " seconds gets ctrl+c and the terminal "
                   "stays open; for longer jobs start them in the background with output in a file (nohup python "
                   "job.py > job.log 2>&1 &). `exit` or `set -e` with a failing command ends the terminal; the next "
                   "call opens a new one. Terminals end when the sandbox stops or restarts (mount_project too).",
    "parameters": {"type": "object",
                   "properties": {"command": {"type": "string", "description": "the bash command, e.g. cd src && ls"},
                                  "terminal": {"type": "string",
                                               "description": "which terminal (default: main). a new name opens a new "
                                                              "one"}},
                   "required": ["command"]},
}
