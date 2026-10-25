# tools/sandbox/mount_project.py — mount one project into this instance's sandbox. the logic is in classes/sandbox.py


def run(agent, name):
    return agent.sandbox.mount(name)


TOOL = {
    "name": "mount_project",
    "description": "Mount a project folder into this instance's sandbox, at /workspace/<name>. It becomes the working "
                   "folder. One project at a time: mounting another one unmounts the current one. A project another "
                   "instance has mounted can't be mounted. This RESTARTS the sandbox (a running one can't get a new "
                   "folder): whatever was installed or started inside is gone, open notebooks are closed. So mount "
                   "first, then install and work.",
    "parameters": {"type": "object",
                   "properties": {"name": {"type": "string", "description": "the project folder, e.g. website"}},
                   "required": ["name"]},
}
