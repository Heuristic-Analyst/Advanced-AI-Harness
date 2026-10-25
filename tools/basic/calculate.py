# tools/calculate.py — a tool: something the model can ask for, and we run.
# every tool file has two things:
#   TOOL  what the model sees: the name, when to use it, and its arguments
#   run   what we execute. it always gets the calling agent first, then the arguments the model passed.
#         whatever it returns goes back to the model as text
# the model never runs anything itself: it only asks, and this code decides what really happens.

import sys
import subprocess

TIMEOUT = 5                                          # seconds. a safety net for something huge like 9**9**9**9
ALLOWED = set("0123456789+-*/().% ")                 # the only characters an expression may have


def run(agent, expression):
    if not set(expression) <= ALLOWED:               # CHECK: is every character in it an allowed one?
        return "invalid expression: only digits, spaces and + - * / ( ) . % are allowed"   # no letters = no code
    try:                                             # calculated in its own small python process: one that runs
        done = subprocess.run([sys.executable, "-I", "-c", "print(eval(input()))"],   # too long can be stopped
                              input=expression + "\n", capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:                # e.g. 9**9**9**9: the process is stopped
        return "too big: no result after " + str(TIMEOUT) + " seconds"
    if done.returncode != 0:                         # it failed, e.g. 1/0 -> "error: ZeroDivisionError: division by zero"
        lines = done.stderr.strip().splitlines()
        return "error: " + (lines[-1] if lines else "exit code " + str(done.returncode))
    return done.stdout.strip()                       # the result, e.g. "397.8"


TOOL = {
    "name": "calculate",
    "description": "Evaluate a math expression and get the exact result, e.g. 2 * (3 + 4) or 0.17 * 2340. "
                   "Use it for every calculation instead of calculating in your head.",
    "parameters": {"type": "object",
                   "properties": {"expression": {"type": "string",
                                                 "description": "only digits, spaces and + - * / ( ) . % "
                                                                "(** is a power, % the remainder of a division)"}},
                   "required": ["expression"]},
}
