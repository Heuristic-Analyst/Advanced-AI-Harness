# tools/sandbox/close_terminal.py — close a terminal (see terminal.py next to this file). the logic is in
# classes/sandbox.py (close_terminal)


def run(agent, terminal=None):
    return agent.sandbox.close_terminal(terminal)


TOOL = {
    "name": "close_terminal",
    "description": "Close a terminal opened with the terminal tool: its folder and variables are gone. Programs it "
                   "started in the background keep running. No name: close every open terminal. Not needed when you "
                   "are done anyway (they end with the sandbox), but frees a place when 4 are open, or gives a fresh "
                   "start.",
    "parameters": {"type": "object",
                   "properties": {"terminal": {"type": "string",
                                               "description": "which terminal, e.g. main. leave it out to close all"}}},
}
