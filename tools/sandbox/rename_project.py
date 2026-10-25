# tools/sandbox/rename_project.py — rename a project folder nobody has mounted. the logic is in classes/sandbox.py


def run(agent, name, new_name):
    return agent.sandbox.rename_project(name, new_name)


TOOL = {
    "name": "rename_project",
    "description": "Rename a project folder in the user's Shared Folder. Not possible while any sandbox has it mounted "
                   "(yours too: unmount_project first). Only when the user asked for it. Tell the user in one short "
                   "sentence what you renamed.",
    "parameters": {"type": "object",
                   "properties": {"name": {"type": "string", "description": "the project's name now"},
                                  "new_name": {"type": "string", "description": "letters, digits, - _ . only"}},
                   "required": ["name", "new_name"]},
}
