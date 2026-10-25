# tools/sandbox/delete_project.py — delete a project folder with everything in it. the logic is in classes/sandbox.py


def run(agent, name):
    return agent.sandbox.delete_project(name)


TOOL = {
    "name": "delete_project",
    "description": "Delete a project folder in the user's Shared Folder, with EVERYTHING in it. It can't be undone: only "
                   "when the user asked you to delete that project. Not possible while any sandbox has it mounted (yours "
                   "too: unmount_project first). Tell the user in one short sentence what you deleted.",
    "parameters": {"type": "object",
                   "properties": {"name": {"type": "string", "description": "the project folder"}},
                   "required": ["name"]},
}
