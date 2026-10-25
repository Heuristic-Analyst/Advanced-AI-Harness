# sandbox.py — the Sandbox: a throwaway Linux container (podman) where the agent runs everything: code, installs,
# notebooks. the agent never runs anything on your computer itself: its tools only ASK, and every command goes into
# this container.
#
# how it works:
#   - each folder in Sandboxes/ is one sandbox, and its Containerfile is all there is. opening a sandbox builds an IMAGE
#     from that file (podman's cache makes this quick when nothing changed) and starts a CONTAINER from it: a throwaway
#     copy that is deleted when it stops. nothing installed at runtime survives a stop
#   - every running main.py (an "instance") has at most one container, opened and closed by the agent with its tools
#   - a container sees only these folders of your computer, all mounted noexec (nothing in them can be run directly
#     from inside, only through an interpreter, e.g. python x.py) and nosuid, nodev:
#       Shared Folder/Common            -> /workspace/Common           always, read-write, shared by every instance
#       Shared Folder/Notebook_Engine   -> /workspace/Notebook_Engine  always, READ-ONLY: the notebook engine's code
#       Shared Folder/<project>         -> /workspace/<project>        at most one, mounted by the agent. while this
#                                                                      instance has it, no other instance can mount it
#   - the network is OFF whenever the agent opens a sandbox. only you can switch it on (/sandbox net on)
#   - podman can't add or remove a folder of a running container, so mounting or unmounting a project restarts it
#   - every container carries labels: which instance started it, which sandbox, which project, which copy of this
#     program. that is how an instance finds its own container, and how the leftovers of a crashed instance are found
#     and removed. containers you start yourself have no such labels and are never touched
#   - who has which project is decided by a lock (functions/locks.py): taking it is one step, so two instances can never
#     both get the same project, and the operating system frees it when an instance ends, however it ends
#
# main.py makes ONE Sandbox for the whole run and hands it to every Agent (agent.sandbox). the tools in tools/sandbox/
# and tools/notebook/ use it from there. everything that talks to podman is in here.

import os
import re
import json
import shutil
import hashlib
import threading
import subprocess
from functions import locks

PROJECT_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"           # what a project folder must be called to be used by the tools
SANDBOX_NAME = r"[a-z0-9]+(-[a-z0-9]+)*"                # what podman accepts in an image name: lowercase, digits, -
NETWORK = "podman"                                      # podman's own network. connected = internet, disconnected = none


class Sandbox:
    def __init__(self, sandboxes_dir, shared_dir, common, engine, instance, command="podman",
                 memory="2g", cpus="2", pids=512, timeout=600):
        self.sandboxes_dir = sandboxes_dir     # Sandboxes/: one folder with a Containerfile per sandbox
        self.shared_dir = shared_dir           # Shared Folder/: the only folder of your computer a sandbox sees parts of
        self.shared_id = os.path.realpath(shared_dir)   # written on every container: two copies of this program on one
                                               # computer never touch each other's containers
        self.common = common                   # "Common": always mounted, shared by every instance
        self.engine = engine                   # "Notebook_Engine": always mounted, read-only
        self.instance = instance               # this instance's id (config.INSTANCE)
        self.command = command                 # "podman"
        self.memory = memory                   # limits for the container
        self.cpus = cpus
        self.pids = pids
        self.timeout = timeout                 # seconds a command may run inside
        self.container = None                  # this instance's container, e.g. harness-python-48213-2026...-1. None = none
        self.name = None                       # its sandbox, e.g. "python"
        self.project = None                    # the mounted project, e.g. "website". None = none
        self.network = False                   # internet on? off whenever the agent opens a sandbox. only you switch it on
        self.notebooks = {}                    # the open notebooks: "Common/sales.ipynb" -> its lock name
        self.notes = []                        # what YOU changed with /sandbox: told to the model with your next message
        self.lost = None                       # the sandbox stopped by itself (out of memory, removed by hand): which one
        self.starts = 0                        # containers this instance started so far, for their names
        self.lock = threading.RLock()          # tools run in parallel: one opens, closes, mounts or changes a project at
                                               # a time. RLock: these functions call each other while holding it

    # --- podman: every command to it goes through here ---
    def podman(self, *args, timeout=None):
        """run one podman command. returns (exit code, what it printed). never raises"""
        try:
            done = subprocess.run([self.command] + list(args), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=timeout)
        except FileNotFoundError:
            return 127, self.command + " is not installed"
        except subprocess.TimeoutExpired:
            return 124, self.command + " gave no answer within " + str(timeout) + " seconds"
        return done.returncode, (done.stdout + done.stderr).strip()

    def available(self):
        """is podman installed and running? (on mac and windows: `podman machine start` once)"""
        return self.podman("info", "--format", "{{.Host.Arch}}", timeout=60)[0] == 0

    # --- folders ---
    def folder(self, name):
        return os.path.join(self.shared_dir, name)

    def engine_ready(self):
        return os.path.isfile(os.path.join(self.folder(self.engine), "client.py"))

    def workdir(self):
        """where commands start inside: the project if one is mounted, otherwise Common"""
        return "/workspace/" + (self.project or self.common)

    def volume(self, folder, options):
        """the --volume value for one folder of Shared Folder. noexec: nothing in it can be run directly from inside"""
        return self.folder(folder) + ":/workspace/" + folder + ":" + options + ",noexec,nosuid,nodev"

    # --- the sandboxes: the folders in Sandboxes/ ---
    def sandboxes(self):
        """every folder in Sandboxes/ with a Containerfile: name -> None if it can be used, otherwise why not"""
        found = {}
        if os.path.isdir(self.sandboxes_dir):
            for name in sorted(os.listdir(self.sandboxes_dir)):
                if os.path.isfile(os.path.join(self.sandboxes_dir, name, "Containerfile")):
                    found[name] = None if re.fullmatch(SANDBOX_NAME, name) else \
                        "can't be used: a sandbox's folder name must be lowercase letters, digits and - (the user can rename it)"
        return found

    def names(self):
        return [name for name, problem in self.sandboxes().items() if problem is None]

    def image(self, name):
        return "localhost/harness-sandbox-" + name

    def containerfile(self, name):
        with open(os.path.join(self.sandboxes_dir, name, "Containerfile"), encoding="utf-8", errors="replace") as f:
            return f.read().strip()

    # --- every container of this program, in any instance: found by their labels ---
    def containers(self):
        """the containers this copy of the program started, in any instance: [{"name", "owner", "sandbox", "project"}]"""
        code, out = self.podman("ps", "--all", "--filter", "label=harness.owner", "--format", "json", timeout=60)
        if code != 0 or not out:
            return []
        try:
            listed = json.loads(out)
        except ValueError:                             # not json: podman printed an error
            return []
        found = []
        for c in listed:
            labels = c.get("Labels") or {}             # "or {}": podman writes null when there are none
            if labels.get("harness.shared") != self.shared_id:   # another copy of this program: not ours to touch
                continue
            found.append({"name": (c.get("Names") or [""])[0], "owner": labels.get("harness.owner", ""),
                          "sandbox": labels.get("harness.sandbox", ""), "project": labels.get("harness.project", "")})
        return found

    def cleanup(self):
        """remove leftover containers: the ones of instances that are gone (a crash, a killed terminal), and old ones of
        this instance. containers of instances that still run are never touched"""
        for c in self.containers():
            old_one_of_mine = c["owner"] == self.instance and c["name"] != self.container
            if old_one_of_mine or not locks.alive(c["owner"]):
                self.podman("rm", "--force", c["name"], timeout=60)

    # --- starting and stopping this instance's container ---
    def build(self, name):
        """build the image from the Containerfile. None if it worked, otherwise the end of the build's output"""
        print("[sandbox] building " + name + " from Sandboxes/" + name + "/Containerfile (quick if nothing changed) ...")
        code, out = self.podman("build", "--tag", self.image(name), os.path.join(self.sandboxes_dir, name), timeout=1800)
        if code != 0:
            return "the build of " + name + " failed. the end of its output:\n" + out[-2000:]
        return None

    def start(self, name, project):
        """start a new container of this sandbox, with Common, the engine and (if given) the project mounted.
        the caller holds the project's lock. returns None if it runs, otherwise why not"""
        self.cleanup()
        problem = self.build(name)
        if problem:
            return problem
        os.makedirs(self.folder(self.common), exist_ok=True)
        self.starts += 1
        container = "harness-" + name + "-" + self.instance + "-" + str(self.starts)   # never clashes with another
        args = ["run", "--detach", "--rm", "--name", container,                        # --rm: deleted when it stops
                "--label", "harness.owner=" + self.instance,
                "--label", "harness.sandbox=" + name,
                "--label", "harness.shared=" + self.shared_id,
                "--network", NETWORK,                  # born on the network, sealed right below (only podman's network
                                                       # can be switched later; a container born without one can't)
                "--entrypoint", "sleep",               # the only thing that runs inside until a command comes: nothing
                                                       # can use the network before it is sealed
                "--security-opt", "no-new-privileges", # no way to gain more rights than it starts with
                "--init",                              # a tiny first process that cleans up ended background programs
                "--pids-limit", str(self.pids), "--memory", self.memory, "--cpus", self.cpus,
                "--volume", self.volume(self.common, "z,rw")]   # z = other containers may share it
        if self.engine_ready():                        # missing: the sandbox still works, only notebooks don't
            args += ["--volume", self.volume(self.engine, "z,ro")]   # ro = read-only: the agent can't change the engine
        if project:
            args += ["--label", "harness.project=" + project,
                     "--volume", self.volume(project, "Z,rw")]          # Z = only this container
        args += ["--workdir", "/workspace/" + (project or self.common), self.image(name), "infinity"]   # sleep infinity
        code, out = self.podman(*args, timeout=180)
        if code != 0:
            return "could not start " + name + ": " + out[-1500:]
        self.container = container
        self.name = name
        self.project = project
        self.lost = None
        if not self.set_network(self.network):         # off (or on again after a restart, if you had switched it on)
            self.stop()
            return ("the sandbox was stopped again, because its network could not be switched "
                    + ("on" if self.network else "off") + ". tell the user")
        return None

    def stop(self):
        if self.container:
            code, out = self.podman("stop", "--time", "2", self.container, timeout=60)   # deleted by itself (--rm)
            if code != 0:
                self.podman("rm", "--force", self.container, timeout=60)
        self.forget()

    def forget(self):
        """this instance has no container anymore: its project and its notebooks are free again"""
        if self.project:
            locks.release(self.project_lock(self.project))
        for lock in list(self.notebooks.values()):    # the kernels died with the container
            locks.release(lock)
        self.notebooks.clear()
        self.container = None
        self.name = None
        self.project = None

    def running(self):
        """the sandbox running in this instance, or None. asked from podman, so one that died meanwhile is noticed"""
        with self.lock:                                # waits while a mount or unmount restarts the container
            if not self.container:
                return None
            code, out = self.podman("container", "inspect", "--format", "{{.State.Running}}", self.container, timeout=60)
            if code == 0 and out == "true":
                return self.name
            self.lost = self.name                      # gone (out of memory, removed by hand): it holds nothing anymore
            self.podman("rm", "--force", self.container, timeout=60)
            self.forget()
            return None

    def not_running(self):
        """the answer for a tool that needs a running sandbox"""
        text = "no sandbox runs in this instance. "
        if self.lost:
            text = ("the sandbox " + self.lost + " stopped by itself (most often: out of memory). everything inside it is "
                    "gone, the files in Shared Folder stay. ")
        return text + "start one with open_sandbox (check_sandbox shows which there are)"

    # --- the network: off whenever the agent opens a sandbox. only the user switches it on ---
    def network_state(self):
        """True = connected, False = not, None = podman couldn't say"""
        code, out = self.podman("inspect", "--format", "{{json .NetworkSettings.Networks}}", self.container, timeout=60)
        if code != 0:
            return None
        return '"' + NETWORK + '"' in out

    def set_network(self, on):
        """connect or disconnect the container, then CHECK. True only if it is now as asked"""
        if not self.container:
            return False
        state = self.network_state()
        if state is None:
            return False
        if on and not state:
            self.podman("network", "connect", NETWORK, self.container, timeout=60)
        if not on and state:
            self.podman("network", "disconnect", NETWORK, self.container, timeout=60)
        return self.network_state() == on

    # --- running commands inside ---
    def exec(self, command, timeout=None):
        """run a bash command inside this instance's container, in the working folder. returns what it printed"""
        timeout = timeout or self.timeout
        if not self.running():
            return self.not_running()
        code, out = self.podman("exec", "--workdir", self.workdir(), self.container,
                                "timeout", "-k", "5", str(timeout), "bash", "-c", command,   # stopped inside, killed 5 s
                                timeout=timeout + 15)                                         # later; and a limit outside
        if code == 124:
            return (out + "\n" if out else "") + "error: stopped after " + str(timeout) + " seconds"
        if code == 127 and not out:
            return "(exit code 127: a command was not found)"
        if code != 0:
            return (out + "\n" if out else "") + "(exit code " + str(code) + ")"
        return out or "(no output)"

    def shell(self):
        """an interactive root shell inside, for you (/sandbox shell)"""
        if not self.running():
            return "no sandbox runs in this instance"
        print("[sandbox] you are root inside " + self.name + ", in " + self.workdir() + ". type exit to come back.")
        try:
            subprocess.run([self.command, "exec", "-it", "--workdir", self.workdir(), self.container, "bash"])
        except FileNotFoundError:
            return self.command + " is not installed"
        return "back in the chat"

    def shutdown(self):
        """at exit: stop this instance's container. its project is free again. nothing to save"""
        with self.lock:
            if self.container:
                print("[sandbox] stopping " + self.name)
                self.stop()

    # --- projects: the folders directly in Shared Folder, except Common and Notebook_Engine ---
    def project_lock(self, name):
        return "project-" + name.lower()               # lowercase: on mac and windows Web and web are one folder

    def reserved(self, name):
        return name.lower() in (self.common.lower(), self.engine.lower())

    def projects(self):
        """the project folders. links to folders elsewhere are not projects: a sandbox could reach outside through them"""
        found = []
        if os.path.isdir(self.shared_dir):
            for name in sorted(os.listdir(self.shared_dir)):
                path = self.folder(name)
                if not self.reserved(name) and not name.startswith(".") and os.path.isdir(path) \
                        and not os.path.islink(path):
                    found.append(name)
        return found

    def name_problem(self, name):
        """None if this is a good name for a project, otherwise why not"""
        if not isinstance(name, str) or not name:
            return "give the project's name"
        if name.lower() == self.common.lower():
            return (self.common + " is not a project: it is mounted in every sandbox, at /workspace/" + self.common
                    + ", and no tool creates, renames, deletes, mounts or unmounts it")
        if name.lower() == self.engine.lower():
            return (self.engine + " is not a project: it holds the notebook engine, read-only, and no tool creates, "
                    "renames, deletes, mounts or unmounts it")
        if not re.fullmatch(PROJECT_NAME, name) or len(name) > 60:
            return "invalid project name: letters, digits, - _ . only, at most 60 characters, e.g. sales-2026"
        return None

    def find_project(self, name):
        """(the existing project's real name, None), or (None, why not). the same name in another spelling is accepted"""
        problem = self.name_problem(name)
        if problem:
            return None, problem
        existing = self.projects()
        if name in existing:
            return name, None
        same = [p for p in existing if p.lower() == name.lower()]
        if len(same) == 1:
            return same[0], None
        return None, ("no project called '" + name + "'. projects: " + (", ".join(existing) or "none yet")
                      + ". create_project makes a new one")

    def holder(self, project):
        """who has this project mounted: "you", "another instance", or None = it is free"""
        if self.project and self.project.lower() == project.lower():
            return "you"
        if not locks.is_free(self.project_lock(project)):
            return "another instance"
        return None

    # --- what the agent and you see ---
    def status_line(self):
        """one line: the state right now. the tools that change it end their answer with it"""
        if not self.container:
            return "[now: no sandbox runs]"
        return ("[now: sandbox " + self.name + " runs, project " + (self.project or "none")
                + ", working folder " + self.workdir() + ", network " + ("on" if self.network else "off")
                + ", open notebooks: " + (", ".join(self.notebooks) or "none") + "]")

    def where(self):
        """what the container sees, in words"""
        text = ("/workspace/" + self.common + " = Shared Folder/" + self.common + " (kept, shared with every other "
                "instance); /workspace/" + self.engine + " = the notebook engine (read-only); ")
        if self.project:
            text += ("/workspace/" + self.project + " = Shared Folder/" + self.project + " (kept, your project, no other "
                     "instance can mount it now); ")
        else:
            text += "no project mounted; "
        return text + "everything else inside is gone when the sandbox stops"

    def snapshot(self):
        """the workspace for the system prompt: built whenever the system prompt is built (a new conversation, /open, a
        checkpoint), so a fresh context always knows what runs. tool results after it are newer"""
        here = self.running()
        lines = ["Your sandbox: a throwaway Linux container where everything you run happens (sandbox_shell, notebooks). "
                 "You can't run anything on the user's computer. Inside it, only /workspace/" + self.common
                 + " and a mounted project are kept; everything else is gone when it stops.",
                 "As it was when this context started (tool results after this are newer):"]
        if here:
            lines.append("- running: " + here + ", working folder " + self.workdir())
            lines.append("- project: " + (self.project + " mounted at /workspace/" + self.project if self.project
                                          else "none mounted"))
            lines.append("- network: " + ("on" if self.network else "off (only the user can switch it on)"))
            lines.append("- open notebooks: " + (", ".join(self.notebooks) or "none"))
        else:
            lines.append("- no sandbox runs. open one with open_sandbox when you need to run something")
        lines.append("- sandboxes: " + (", ".join(self.names()) or "none") + ". projects: "
                     + (", ".join(self.projects()) or "none yet"))
        return "\n".join(lines)

    def take_notes(self):
        """what the user changed with /sandbox since the model's last message, and forget it"""
        notes, self.notes = self.notes, []
        return notes

    def built_at(self, name):
        code, out = self.podman("image", "inspect", "--format", "{{.Created}}", self.image(name), timeout=60)
        return out[:19] if code == 0 and out else None

    def others_running(self, name):
        """how many OTHER instances run this sandbox right now"""
        return sum(1 for c in self.containers() if c["sandbox"] == name and c["owner"] != self.instance)

    # --- the agent's tools (tools/sandbox/) ---
    def check(self, name=None):
        """check_sandbox: every sandbox (or one) with its whole Containerfile, and what runs here. changes nothing"""
        if not self.available():
            return self.command + " is not installed or not running, so there are no sandboxes right now. tell the user"
        found = self.sandboxes()
        if name and name not in found:
            return "no sandbox called '" + name + "'. sandboxes: " + (", ".join(found) or "none")
        if not found:
            return "no sandboxes yet. the user makes one: a folder in Sandboxes/ with a Containerfile inside"
        here = self.running()
        self.cleanup()
        lines = ["running in this instance: " + (here if here else "none") + ". one sandbox per instance.",
                 "every start builds the image from its Containerfile again: what is below is exactly what you get. "
                 "nothing installed at runtime is kept."]
        for each in ([name] if name else list(found)):
            lines.append("")
            lines.append("=== sandbox: " + each + " ===")
            if found[each]:
                lines.append(found[each])
            built = self.built_at(each)
            lines.append("image: " + ("built " + built if built else "not built yet: the first start builds it, "
                                                                       "which can take a while"))
            lines.append("state: " + ("running here" if each == here else "not running here"))
            others = self.others_running(each)
            if others:
                lines.append("also running in " + str(others) + " other instance(s), each in its own container")
            lines.append("Containerfile:")
            lines.append(self.containerfile(each) or "(empty)")
        return "\n".join(lines) + "\n\n" + self.status_line()

    def open(self, name, project=None):
        """open_sandbox: build and start this sandbox for this instance, optionally with a project mounted"""
        with self.lock:
            if not self.available():
                return self.command + " is not installed or not running, so there are no sandboxes right now. tell the user"
            here = self.running()
            if here:
                return ("a sandbox already runs in this instance: " + here + ". only one per instance: use it, or "
                        "close_sandbox first. (to mount a project into it: mount_project)\n" + self.status_line())
            found = self.sandboxes()
            if name not in found:
                return "no sandbox called '" + str(name) + "'. sandboxes: " + (", ".join(found) or "none")
            if found[name]:
                return name + " " + found[name]
            real = None
            if project:
                real, problem = self.find_project(project)
                if problem:
                    return problem
                if not locks.take(self.project_lock(real)):
                    return (real + " is mounted by another instance right now. pick another project, or open the "
                            "sandbox without one")
            self.network = False                       # every sandbox the agent opens starts without internet
            problem = self.start(name, real)
            if problem:
                if real:
                    locks.release(self.project_lock(real))
                return problem
            return "running " + name + ", network off. " + self.where() + "\n" + self.status_line()

    def close(self):
        """close_sandbox: stop it. its project is free for other instances again"""
        with self.lock:
            here = self.running()
            if not here:
                return self.not_running()
            project = self.project
            self.stop()
            answer = ("stopped " + here + ". everything installed or started inside is gone; the files in "
                      "Shared Folder/" + self.common + (" and Shared Folder/" + project if project else "") + " stay")
            if project:
                answer += ". " + project + " is free for other instances again"
            return answer + "\n" + self.status_line()

    def restart(self, project):
        """podman can't add or remove a folder of a running container: stop it and start a new one. the network stays"""
        name = self.name
        self.stop()                                    # releases the old project's lock
        problem = self.start(name, project)
        if problem:
            return "the sandbox was stopped, but could not start again: " + problem
        return ("restarted " + name + ": whatever was installed or started inside since its start is gone, open "
                "notebooks were closed (nb_open them again). " + self.where())

    def mount(self, project):
        """mount_project: mount one project (another one mounted is unmounted). restarts the sandbox"""
        with self.lock:
            if not self.running():
                return "no sandbox runs in this instance. open_sandbox can mount the project right away"
            real, problem = self.find_project(project)
            if problem:
                return problem
            if real == self.project:
                return real + " is mounted already, at /workspace/" + real + "\n" + self.status_line()
            if not locks.take(self.project_lock(real)):
                return real + " is mounted by another instance right now. pick another project, or try again later"
            old = self.project
            answer = self.restart(real)
            if not self.container:                     # it didn't start again: nothing holds the new project
                locks.release(self.project_lock(real))
            elif old:
                answer = "unmounted " + old + " (free for other instances again), mounted " + real + ". " + answer
            else:
                answer = "mounted " + real + ". " + answer
            return answer + "\n" + self.status_line()

    def unmount(self):
        """unmount_project: unmount the project. restarts the sandbox"""
        with self.lock:
            if not self.running():
                return self.not_running()
            if not self.project:
                return ("no project is mounted. (" + self.common + " and " + self.engine + " are always mounted, they "
                        "can't be unmounted)\n" + self.status_line())
            old = self.project
            return "unmounted " + old + ", it is free for other instances again. " + self.restart(None) + "\n" \
                + self.status_line()

    def check_projects(self):
        """check_projects: every project folder, and who has it mounted"""
        lines = ["projects are the folders directly in the user's Shared Folder. a sandbox mounts one at a time, at "
                 "/workspace/<project>, and while it does, no other instance can mount it.",
                 self.common + " and " + self.engine + " are not projects: they are always mounted (" + self.engine
                 + " read-only), and no tool changes them."]
        if self.available():
            self.running()
            self.cleanup()                             # a crashed instance's container must not seem to hold anything
        names = self.projects()
        if not names:
            lines.append("projects: none yet. create_project makes one")
        else:
            lines.append("projects:")
            for name in names:
                if not re.fullmatch(PROJECT_NAME, name) or len(name) > 60:
                    state = ("can't be used: its name has other characters than letters, digits, - _ . "
                             "(the user can rename it)")
                else:
                    state = {"you": "mounted by you", "another instance": "mounted by another instance, not available now",
                             None: "free"}[self.holder(name)]
                lines.append("- " + name + ": " + state)
        return "\n".join(lines) + "\n" + self.status_line()

    def create_project(self, name):
        """create_project: a new, empty folder Shared Folder/<name>"""
        with self.lock:
            problem = self.name_problem(name)
            if problem:
                return problem
            for existing in os.listdir(self.shared_dir) if os.path.isdir(self.shared_dir) else []:
                if existing.lower() == name.lower():
                    return "'" + existing + "' exists already in Shared Folder: use it, or pick another name"
            os.makedirs(self.folder(name))
            return ("created project " + name + " (Shared Folder/" + name + "). mount_project mounts it, or open_sandbox "
                    "with project=" + name + "\n" + self.status_line())

    def rename_project(self, name, new_name):
        """rename_project: rename a project folder nobody has mounted"""
        with self.lock:
            real, problem = self.find_project(name)
            if problem:
                return problem
            problem = self.name_problem(new_name)
            if problem:
                return problem
            for existing in os.listdir(self.shared_dir):
                if existing.lower() == new_name.lower() and existing != real:
                    return "'" + existing + "' exists already in Shared Folder: pick another name"
            if real == self.project:
                return real + " is mounted in your sandbox: unmount_project first, then rename it"
            if self.available():
                self.cleanup()                         # a crashed instance's container must not keep it mounted
            if not locks.take(self.project_lock(real)):   # held while renaming: nobody can mount it meanwhile
                return real + " is mounted by another instance right now: it can only be renamed when nobody has it"
            try:
                os.rename(self.folder(real), self.folder(new_name))
            finally:
                locks.release(self.project_lock(real))
            return "renamed project " + real + " -> " + new_name + " (Shared Folder/" + new_name + ")\n" + self.status_line()

    def delete_project(self, name):
        """delete_project: delete a project folder with everything in it, if nobody has it mounted"""
        with self.lock:
            real, problem = self.find_project(name)
            if problem:
                return problem
            if real == self.project:
                return real + " is mounted in your sandbox: unmount_project first, then delete it"
            if self.available():
                self.cleanup()
            if not locks.take(self.project_lock(real)):   # held while deleting: nobody can mount it meanwhile
                return real + " is mounted by another instance right now: it can only be deleted when nobody has it"
            try:
                shutil.rmtree(self.folder(real))       # the folder and everything in it. there is no undo
            finally:
                locks.release(self.project_lock(real))
            return "deleted project " + real + " and everything in it\n" + self.status_line()

    # --- notebooks: which ones are open here (tools/notebook/_notebook.py) ---
    def notebook_lock(self, path):
        return "notebook-" + hashlib.md5(path.lower().encode()).hexdigest()[:12]   # a safe file name for any path

    def claim_notebook(self, path):
        """lock a notebook for this instance before its kernel starts. False = another instance has it open"""
        lock = self.notebook_lock(path)
        if not locks.take(lock):
            return False
        self.notebooks[path] = lock
        return True

    def free_notebook(self, path):
        lock = self.notebooks.pop(path, None)
        if lock:
            locks.release(lock)

    # --- your /sandbox commands (main.py) ---
    def overview(self):
        """/sandbox: what runs here, and every sandbox"""
        if not self.available():
            return self.command + " is not installed or not running, so there are no sandboxes right now"
        here = self.running()
        self.cleanup()
        lines = [self.status_line(), "sandboxes:"]
        for name, problem in self.sandboxes().items():
            marks = ""
            if name == here:
                marks += " (running here)"
            others = 0 if problem else self.others_running(name)
            if others:
                marks += " (running in " + str(others) + " other instance(s))"
            if problem:
                marks += " (" + problem + ")"
            elif not self.built_at(name):
                marks += " (not built yet)"
            lines.append("  " + name + marks)
        if not self.sandboxes():
            lines.append("  none. a new sandbox: a folder in Sandboxes/ with a Containerfile inside")
        return "\n".join(lines)

    def user_network(self, on):
        """/sandbox net on|off"""
        with self.lock:
            if not self.running():
                return "no sandbox runs in this instance"
            if not self.set_network(on):
                return "could not switch the network " + ("on" if on else "off") + ". " + \
                    ("it is on" if self.network_state() else "it is off")
            self.network = on
            self.notes.append("[from the program, not the user] The user switched the sandbox's network "
                              + ("ON: the sandbox can reach the internet now (e.g. pip install)." if on else
                                 "OFF: the sandbox can't reach the internet anymore."))
            return "network " + ("on" if on else "off") + " (until the agent opens a new sandbox, or you switch it)"

    def user_close(self):
        """/sandbox close"""
        with self.lock:
            here = self.running()
            if not here:
                return "no sandbox runs in this instance"
            self.stop()
            self.notes.append("[from the program, not the user] The user closed the sandbox (" + here + "). Everything "
                              "inside it is gone, open notebooks are closed; the files in Shared Folder stay.")
            return "stopped " + here
