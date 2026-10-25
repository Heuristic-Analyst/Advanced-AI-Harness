# tools/sandbox/check_projects.py — the project folders and who has them. changes nothing. logic: classes/sandbox.py


def run(agent):
    return agent.sandbox.check_projects()


TOOL = {
    "name": "check_projects",
    "description": "List the project folders in the user's Shared Folder, and for each whether it is free, mounted by "
                   "you, or mounted by another running instance (then you can't mount it now). Call it before "
                   "create_project, mount_project, or open_sandbox with a project.",
    "parameters": {"type": "object", "properties": {}},
}
