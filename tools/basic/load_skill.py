# tools/basic/load_skill.py — gives the model the full instructions of one skill.
# the system prompt only lists each skill's name and one line (the menu). when a task matches, the model calls this,
# and the whole SKILL.md comes back as the tool result: it stays in the conversation, so it is loaded once per task.

from functions.read_text import read_text


def run(agent, name):
    if name not in agent.skills:                             # only a NAME from the menu, never a path from the model:
        return ("no skill called '" + str(name) + "'. yours: "   # so it can never make this read any other file
                + (", ".join(agent.skills) or "none"))
    return read_text(agent.skills[name]["path"])             # the whole SKILL.md, header included


TOOL = {
    "name": "load_skill",
    "description": "Load the full instructions of a skill from the list in your system prompt. "
                   "Call it before you start a task that matches a skill, then follow what it returns.",
    "parameters": {"type": "object",
                   "properties": {"name": {"type": "string", "description": "the skill's name, as in the list"}},
                   "required": ["name"]},
}
