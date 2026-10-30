# sandbox.py — the Sandbox: a throwaway Linux container (podman) where the agent runs everything: code, installs,
# notebooks. the agent never runs anything on your computer itself: its tools only ASK, and every command goes into
# this container.
#
# how it works:
#   - each folder in Sandboxes/ is one sandbox, and its Containerfile is all there is. opening a sandbox builds an IMAGE
#     from that file (podman's cache makes this quick when nothing changed) and starts a CONTAINER from it: a throwaway
#     copy that is deleted when it stops. nothing installed at runtime survives a stop
#   - a sandbox may have settings next to its Containerfile: sandbox.json, written by YOU (memory, cpus, gpu, view).
#     the agent can't change them: Sandboxes/ is never mounted into a sandbox, and no tool writes there. see settings()
#   - every running main.py (an "instance") has at most one container, opened and closed by the agent with its tools
#   - a container sees only these folders of your computer, all mounted noexec (nothing in them can be run directly
#     from inside, only through an interpreter, e.g. python x.py) and nosuid, nodev:
#       Shared Folder/Common            -> /workspace/Common           always, read-write, shared by every instance
#       Shared Folder/Notebook_Engine   -> /workspace/Notebook_Engine  always, READ-ONLY: the notebook engine's code
#       Shared Folder/<project>         -> /workspace/<project>        as many as the agent mounts. while this instance
#                                                                      has one, no other instance can mount it
#     a READ-ONLY project (READONLY_PROJECTS in config.py, e.g. Browser) is mounted read-only, except the subfolders
#     named there (e.g. Browser/tmp). no tool creates, renames or deletes it
#   - "view" (sandbox.json): a port inside the sandbox you can open in your own browser, through classes/relay.py
#   - the network is OFF whenever the agent opens a sandbox. only you can switch it on (/sandbox net on)
#   - podman can't add or remove a folder of a running container, so mounting or unmounting a project restarts it
#   - every container carries labels: which instance started it, which sandbox, which projects, which copy of this
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
from classes.relay import Relay
from classes.terminal import Terminal

PROJECT_NAME = r"[A-Za-z0-9][A-Za-z0-9._-]*"           # what a project folder must be called to be used by the tools
SANDBOX_NAME = r"[a-z0-9]+(-[a-z0-9]+)*"                # what podman accepts in an image name: lowercase, digits, -
NETWORK = "podman"                                      # podman's own network. connected = internet, disconnected = none
SETTINGS = "sandbox.json"                               # Sandboxes/<name>/sandbox.json: that sandbox's settings (optional)
MEMORY = r"[1-9][0-9]*[kmgKMG]"                         # a memory size podman understands: 512m, 4g
TERMINAL_NAME = r"[A-Za-z0-9_-]{1,30}"                  # what a terminal may be called: main, server, build-2
TERMINALS = 4                                           # terminals open at once, per instance


class Sandbox:
    def __init__(self, sandboxes_dir, shared_dir, common, engine, instance, command="podman",
                 memory="2g", cpus="2", pids=512, timeout=600, readonly=None):
        self.sandboxes_dir = sandboxes_dir     # Sandboxes/: one folder with a Containerfile per sandbox
        self.shared_dir = shared_dir           # Shared Folder/: the only folder of your computer a sandbox sees parts of
        self.shared_id = os.path.realpath(shared_dir)   # written on every container: two copies of this program on one
                                               # computer never touch each other's containers
        self.common = common                   # "Common": always mounted, shared by every instance
        self.engine = engine                   # "Notebook_Engine": always mounted, read-only
        self.instance = instance               # this instance's id (config.INSTANCE)
        self.command = command                 # "podman"
        self.memory = memory                   # limits for the container, unless its sandbox.json says otherwise
        self.cpus = cpus
        self.pids = pids
        self.timeout = timeout                 # seconds a command may run inside
        self.readonly = readonly or {}         # the read-only projects: name -> the subfolders in it that are writable
                                               # (config.READONLY_PROJECTS)
        self.container = None                  # this instance's container, e.g. harness-python-48213-2026...-1. None = none
        self.name = None                       # its sandbox, e.g. "python"
        self.projects = []                     # the mounted projects, in the order they were mounted, e.g. ["website"]
        self.relay = None                      # the door for your browser into the sandbox ("view"). made when first needed
        self.network = False                   # internet on? off whenever the agent opens a sandbox. only you switch it on
        self.notebooks = {}                    # the open notebooks: "Common/sales.ipynb" -> its lock name
        self.terminals = {}                    # the open terminals (shells that stay open): "main" -> its Terminal
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

    def writable_projects(self):
        """the mounted projects the agent can write in: all but the read-only ones"""
        return [p for p in self.projects if self.readonly_of(p) is None]

    def workdir(self):
        """where commands start inside: the first mounted project it can write in, otherwise Common"""
        writable = self.writable_projects()
        return "/workspace/" + (writable[0] if writable else self.common)

    def volume(self, host, inside, options):
        """the --volume value for one folder. noexec: nothing in it can be run directly from inside"""
        return host + ":" + inside + ":" + options + ",noexec,nosuid,nodev"

    def project_volumes(self, project):
        """the --volume arguments for one project. a read-only project: the folder read-only, then each of its writable
        subfolders read-write on top of it (created first, so there is something to mount)"""
        subfolders = self.readonly_of(project)
        if subfolders is None:                             # a normal project: all of it read-write, only this container
            return ["--volume", self.volume(self.folder(project), "/workspace/" + project, "Z,rw")]
        args = ["--volume", self.volume(self.folder(project), "/workspace/" + project, "Z,ro")]
        for sub in subfolders:
            os.makedirs(os.path.join(self.folder(project), sub), exist_ok=True)
            args += ["--volume", self.volume(os.path.join(self.folder(project), sub),
                                             "/workspace/" + project + "/" + sub, "Z,rw")]
        return args

    # --- the sandboxes: the folders in Sandboxes/ ---
    def sandboxes(self):
        """every folder in Sandboxes/ with a Containerfile: name -> None if it can be used, otherwise why not"""
        found = {}
        if os.path.isdir(self.sandboxes_dir):
            for name in sorted(os.listdir(self.sandboxes_dir)):
                if os.path.isfile(os.path.join(self.sandboxes_dir, name, "Containerfile")):
                    if not re.fullmatch(SANDBOX_NAME, name):
                        found[name] = ("can't be used: a sandbox's folder name must be lowercase letters, digits and - "
                                       "(the user can rename it)")
                    else:
                        found[name] = self.settings(name)[1]     # None, or what is wrong with its sandbox.json
        return found

    def names(self):
        return [name for name, problem in self.sandboxes().items() if problem is None]

    def image(self, name):
        return "localhost/harness-sandbox-" + name

    def containerfile(self, name):
        with open(os.path.join(self.sandboxes_dir, name, "Containerfile"), encoding="utf-8", errors="replace") as f:
            return f.read().strip()

    # --- a sandbox's settings: Sandboxes/<name>/sandbox.json, written by you, never by the agent ---
    def settings(self, name):
        """(the settings, None), or ({}, what is wrong). no file: ({}, None) = the defaults from config.py.
        only these keys, each checked, so nothing else can ever reach podman through this file:
            memory  "4g"     how much memory it may use (default SANDBOX_MEMORY in config.py)
            cpus    4        how many CPU cores it may use (default SANDBOX_CPUS)
            gpu     true     it gets the computer's NVIDIA GPUs (needs the NVIDIA Container Toolkit, see Sandboxes/)
            view    6080     a port inside it that you can open in your browser (see classes/relay.py)
            network true     its network is ON when the agent opens it (default: off, only you switch it on)
        keys starting with _ are notes for you, and are skipped"""
        path = os.path.join(self.sandboxes_dir, name, SETTINGS)
        if not os.path.isfile(path):
            return {}, None
        where = "Sandboxes/" + name + "/" + SETTINGS
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except ValueError as e:
            return {}, "can't be used: " + where + " is not valid JSON (" + str(e) + "). the user must fix it"
        except OSError as e:
            return {}, "can't be used: " + where + " can't be read (" + str(e) + ")"
        if not isinstance(data, dict):
            return {}, "can't be used: " + where + " must be one {...} with settings. the user must fix it"
        problems = []
        for key, value in data.items():
            if key.startswith("_"):
                continue
            if key == "memory":
                if not (isinstance(value, str) and re.fullmatch(MEMORY, value)):
                    problems.append('"memory" must be like "4g" or "512m"')
            elif key == "cpus":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                    problems.append('"cpus" must be a number above 0, like 4')
            elif key == "gpu":
                if not isinstance(value, bool):
                    problems.append('"gpu" must be true or false')
            elif key == "view":
                if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
                    problems.append('"view" must be a port number, like 6080')
            elif key == "network":
                if not isinstance(value, bool):
                    problems.append('"network" must be true or false')
            else:
                problems.append('"' + key + '" is not a setting (there are: memory, cpus, gpu, view, network)')
        if problems:
            return {}, "can't be used: " + where + ": " + "; ".join(problems) + ". the user must fix it"
        return {k: v for k, v in data.items() if not k.startswith("_")}, None

    def describe_settings(self, settings, short=False):
        """the settings in words, for check_sandbox and (short) /sandbox"""
        parts = ["memory " + settings.get("memory", self.memory), "cpus " + str(settings.get("cpus", self.cpus)),
                 "GPU " + ("yes" if settings.get("gpu") else "no"),
                 "network " + ("on" if settings.get("network") else "off") + " when opened"]
        if settings.get("view"):
            parts.append("view: port " + str(settings["view"])
                         + ("" if short else " inside can be opened by the user in their own browser"))
        return ", ".join(parts)

    # --- every container of this program, in any instance: found by their labels ---
    def containers(self):
        """the containers this copy of the program started, in any instance: [{"name", "owner", "sandbox", "projects"}]"""
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
                          "sandbox": labels.get("harness.sandbox", ""),
                          "projects": [p for p in labels.get("harness.projects", "").split(",") if p]})
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
        code, out = self.podman("build", "--tag", self.image(name), os.path.join(self.sandboxes_dir, name), timeout=3600)
        if code != 0:
            return "the build of " + name + " failed. the end of its output:\n" + out[-2000:]
        return None

    def start(self, name, projects):
        """start a new container of this sandbox, with Common, the engine and the projects mounted, and the settings of
        its sandbox.json. the caller holds the projects' locks. returns None if it runs, otherwise why not"""
        settings, problem = self.settings(name)
        if problem:
            return name + " " + problem
        self.cleanup()
        problem = self.build(name)
        if problem:
            return problem
        os.makedirs(self.folder(self.common), exist_ok=True)
        memory = settings.get("memory", self.memory)
        self.starts += 1
        container = "harness-" + name + "-" + self.instance + "-" + str(self.starts)   # never clashes with another
        args = ["run", "--detach", "--rm", "--name", container,                        # --rm: deleted when it stops
                "--label", "harness.owner=" + self.instance,
                "--label", "harness.sandbox=" + name,
                "--label", "harness.shared=" + self.shared_id,
                "--label", "harness.projects=" + ",".join(projects),
                "--network", NETWORK,                  # born on the network, sealed right below (only podman's network
                                                       # can be switched later; a container born without one can't)
                "--entrypoint", "sleep",               # the only thing that runs inside until a command comes: nothing
                                                       # can use the network before it is sealed
                "--security-opt", "no-new-privileges", # no way to gain more rights than it starts with
                "--init",                              # a tiny first process that cleans up ended background programs
                "--pids-limit", str(self.pids), "--memory", memory, "--cpus", str(settings.get("cpus", self.cpus)),
                "--shm-size", memory,                  # /dev/shm (shared memory, used by browsers and pytorch): as big as
                                                       # the memory limit. it can't use more anyway: it counts towards it
                "--volume", self.volume(self.folder(self.common), "/workspace/" + self.common, "z,rw")]   # z = other
                                                       # containers may share it
        if settings.get("gpu"):                        # the NVIDIA GPUs, through CDI (the NVIDIA Container Toolkit)
            args += ["--device", "nvidia.com/gpu=all"]
        if self.engine_ready():                        # missing: the sandbox still works, only notebooks don't
            args += ["--volume", self.volume(self.folder(self.engine), "/workspace/" + self.engine, "z,ro")]   # ro =
                                                       # read-only: the agent can't change the engine
        for project in projects:                       # Z = only this container
            args += self.project_volumes(project)
        writable = [p for p in projects if self.readonly_of(p) is None]
        args += ["--workdir", "/workspace/" + (writable[0] if writable else self.common), self.image(name), "infinity"]
        code, out = self.podman(*args, timeout=180)
        if code != 0:
            if settings.get("gpu") and re.search(r"cdi|nvidia", out, re.IGNORECASE):
                return (name + " asks for the GPU (\"gpu\": true in Sandboxes/" + name + "/" + SETTINGS + "), but podman "
                        "can't give it: the NVIDIA Container Toolkit is not set up on this computer (see "
                        "Sandboxes/README.md). tell the user. podman said: " + out[-800:])
            return "could not start " + name + ": " + out[-1500:]
        self.container = container
        self.name = name
        self.projects = list(projects)
        self.lost = None
        if not self.set_network(self.network):         # off (or on again after a restart, if you had switched it on)
            self.stop()
            return ("the sandbox was stopped again, because its network could not be switched "
                    + ("on" if self.network else "off") + ". tell the user")
        if settings.get("view"):                       # the door for your browser: made once, then only pointed
            if not self.relay:
                self.relay = Relay(self.command)
            self.relay.point(container, settings["view"])
        return None

    def stop(self, keep=()):
        """stop the container. keep: projects whose locks stay held (a restart mounts them again)"""
        if self.container:
            code, out = self.podman("stop", "--time", "2", self.container, timeout=60)   # deleted by itself (--rm)
            if code != 0:
                self.podman("rm", "--force", self.container, timeout=60)
        self.forget(keep)

    def forget(self, keep=()):
        """this instance has no container anymore: its projects (except keep) and its notebooks are free again"""
        for project in self.projects:
            if project not in keep:
                locks.release(self.project_lock(project))
        for lock in list(self.notebooks.values()):    # the kernels died with the container
            locks.release(lock)
        self.notebooks.clear()
        for terminal in list(self.terminals.values()):   # they ran inside the container: gone with it
            terminal.close()
        self.terminals.clear()
        if self.relay:                                 # the door leads nowhere until a sandbox with "view" starts
            self.relay.point(None, None)
        self.container = None
        self.name = None
        self.projects = []

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
        """at exit: stop this instance's container and the door into it. its projects are free again. nothing to save"""
        with self.lock:
            if self.container:
                print("[sandbox] stopping " + self.name)
                self.stop()
            if self.relay:
                self.relay.close()

    def view_url(self):
        """where you can open the running sandbox's "view" in your browser, or None"""
        return self.relay.url() if self.relay and self.container else None

    # --- projects: the folders directly in Shared Folder, except Common and Notebook_Engine ---
    def project_lock(self, name):
        return "project-" + name.lower()               # lowercase: on mac and windows Web and web are one folder

    def reserved(self, name):
        return name.lower() in (self.common.lower(), self.engine.lower())

    def readonly_of(self, name):
        """a read-only project: the list of its writable subfolders (maybe empty). a normal project: None"""
        for project, subfolders in self.readonly.items():
            if project.lower() == name.lower():
                return list(subfolders)
        return None

    def readonly_text(self, name):
        subfolders = self.readonly_of(name)
        writable = ", ".join(name + "/" + sub + "/" for sub in subfolders)
        return "read-only for you" + (", except " + writable if writable else "")

    def projects_of_disk(self):
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

    def readonly_problem(self, name, what):
        """None for a normal project. a read-only one: why the agent can't create, rename or delete it"""
        for project in self.readonly:
            if project.lower() == str(name).lower():
                return (project + " is a read-only project: you can mount it and use it, but no tool can " + what
                        + " it. only the user can, by hand")
        return None

    def find_project(self, name):
        """(the existing project's real name, None), or (None, why not). the same name in another spelling is accepted"""
        problem = self.name_problem(name)
        if problem:
            return None, problem
        existing = self.projects_of_disk()
        if name in existing:
            return name, None
        same = [p for p in existing if p.lower() == name.lower()]
        if len(same) == 1:
            return same[0], None
        return None, ("no project called '" + name + "'. projects: " + (", ".join(existing) or "none yet")
                      + ". create_project makes a new one")

    def mounted(self, name):
        """the mounted project with this name (in any spelling), or None"""
        for project in self.projects:
            if project.lower() == str(name).lower():
                return project
        return None

    def holder(self, project):
        """who has this project mounted: "you", "another instance", or None = it is free"""
        if self.mounted(project):
            return "you"
        if not locks.is_free(self.project_lock(project)):
            return "another instance"
        return None

    # --- what the agent and you see ---
    def status_line(self):
        """one line: the state right now. the tools that change it end their answer with it"""
        if not self.container:
            return "[now: no sandbox runs]"
        view = self.view_url()
        return ("[now: sandbox " + self.name + " runs, projects " + (", ".join(self.projects) or "none")
                + ", working folder " + self.workdir() + ", network " + ("on" if self.network else "off")
                + ", open notebooks: " + (", ".join(self.notebooks) or "none")
                + ", open terminals: " + (self.terminals_text() or "none")
                + (", view for the user: " + view if view else "") + "]")

    def where(self):
        """what the container sees, in words"""
        text = ("/workspace/" + self.common + " = Shared Folder/" + self.common + " (kept, shared with every other "
                "instance); /workspace/" + self.engine + " = the notebook engine (read-only); ")
        for project in self.projects:
            if self.readonly_of(project) is None:
                text += ("/workspace/" + project + " = Shared Folder/" + project + " (kept, your project, no other "
                         "instance can mount it now); ")
            else:
                text += ("/workspace/" + project + " = Shared Folder/" + project + " (" + self.readonly_text(project)
                         + ", no other instance can mount it now); ")
        if not self.projects:
            text += "no project mounted; "
        return text + "everything else inside is gone when the sandbox stops"

    def snapshot(self):
        """the workspace for the system prompt: built whenever the system prompt is built (a new conversation, /open, a
        checkpoint), so a fresh context always knows what runs. tool results after it are newer"""
        here = self.running()
        lines = ["Your sandbox: a throwaway Linux container where everything you run happens (sandbox_shell, notebooks). "
                 "You can't run anything on the user's computer. Inside it, only /workspace/" + self.common
                 + " and the mounted projects are kept; everything else is gone when it stops.",
                 "As it was when this context started (tool results after this are newer):"]
        if here:
            lines.append("- running: " + here + ", working folder " + self.workdir())
            lines.append("- projects: " + (", ".join(p + " at /workspace/" + p
                                                     + ("" if self.readonly_of(p) is None
                                                        else " (" + self.readonly_text(p) + ")")
                                                     for p in self.projects) or "none mounted"))
            lines.append("- network: " + ("on" if self.network else "off (only the user can switch it on)"))
            lines.append("- open notebooks: " + (", ".join(self.notebooks) or "none"))
            lines.append("- open terminals: " + (self.terminals_text() or "none"))
            if self.view_url():
                lines.append("- view: the user can watch at " + self.view_url() + " (in their own browser)")
        else:
            lines.append("- no sandbox runs. open one with open_sandbox when you need to run something")
        lines.append("- sandboxes: " + (", ".join(self.names()) or "none") + ". projects: "
                     + (", ".join(self.projects_of_disk()) or "none yet"))
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
            else:
                lines.append("settings (set by the user in " + SETTINGS + ", you can't change them): "
                             + self.describe_settings(self.settings(each)[0]))
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

    def open(self, name, projects=None):
        """open_sandbox: build and start this sandbox for this instance, optionally with projects mounted"""
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
            if isinstance(projects, str):              # one project as text: fine too
                projects = [projects]
            if projects is not None and not isinstance(projects, list):
                return "projects must be a list of project names, e.g. [\"website\"]"
            reals = []
            for project in projects or []:
                real, problem = self.find_project(project)
                if problem:
                    return problem
                if real not in reals:
                    reals.append(real)
            taken = []
            for real in reals:                         # every lock, or none
                if not locks.take(self.project_lock(real)):
                    for t in taken:
                        locks.release(self.project_lock(t))
                    return (real + " is mounted by another instance right now. leave it out, or pick another project "
                            "(check_projects)")
                taken.append(real)
            self.network = self.settings(name)[0].get("network", False)   # off, unless its sandbox.json (yours)
            problem = self.start(name, reals)                             # says "network": true
            if problem:
                for real in reals:
                    locks.release(self.project_lock(real))
                return problem
            return ("running " + name + ", network " + ("on (its sandbox.json, set by the user)" if self.network
                                                        else "off") + ". " + self.where() + "\n" + self.status_line())

    def close(self):
        """close_sandbox: stop it. its projects are free for other instances again"""
        with self.lock:
            here = self.running()
            if not here:
                return self.not_running()
            projects = list(self.projects)
            self.stop()
            answer = ("stopped " + here + ". everything installed or started inside is gone; the files in "
                      "Shared Folder/" + self.common + "".join(" and Shared Folder/" + p for p in projects) + " stay")
            if projects:
                answer += ". " + ", ".join(projects) + (" is" if len(projects) == 1 else " are") \
                          + " free for other instances again"
            return answer + "\n" + self.status_line()

    def restart(self, projects):
        """podman can't add or remove a folder of a running container: stop it and start a new one with these projects.
        their locks stay held through it; if it doesn't start again, they are given back. the network stays"""
        name = self.name
        self.stop(keep=projects)                       # gives back only the locks of projects not in the new list
        problem = self.start(name, projects)
        if problem:
            for project in projects:
                locks.release(self.project_lock(project))
            return "the sandbox was stopped, but could not start again: " + problem
        return ("restarted " + name + ": whatever was installed or started inside since its start is gone, open "
                "notebooks were closed (nb_open them again), open terminals too. " + self.where())

    def mount(self, project):
        """mount_project: mount one more project (the ones mounted stay). restarts the sandbox"""
        with self.lock:
            if not self.running():
                return "no sandbox runs in this instance. open_sandbox can mount projects right away"
            real, problem = self.find_project(project)
            if problem:
                return problem
            if self.mounted(real):
                return real + " is mounted already, at /workspace/" + self.mounted(real) + "\n" + self.status_line()
            if not locks.take(self.project_lock(real)):
                return real + " is mounted by another instance right now. pick another project, or try again later"
            answer = self.restart(self.projects + [real])
            if self.container:
                answer = "mounted " + real + ". " + answer
            return answer + "\n" + self.status_line()

    def unmount(self, project=None):
        """unmount_project: unmount one project (the others stay). restarts the sandbox"""
        with self.lock:
            if not self.running():
                return self.not_running()
            if not self.projects:
                return ("no project is mounted. (" + self.common + " and " + self.engine + " are always mounted, they "
                        "can't be unmounted)\n" + self.status_line())
            if project:
                old = self.mounted(project)
                if not old:
                    return (str(project) + " is not mounted. mounted: " + ", ".join(self.projects) + "\n"
                            + self.status_line())
            elif len(self.projects) == 1:
                old = self.projects[0]
            else:
                return ("several projects are mounted: " + ", ".join(self.projects) + ". say which one to unmount\n"
                        + self.status_line())
            rest = [p for p in self.projects if p != old]
            answer = self.restart(rest)
            if self.container:
                answer = "unmounted " + old + ", it is free for other instances again. " + answer
            return answer + "\n" + self.status_line()

    def check_projects(self):
        """check_projects: every project folder, and who has it mounted"""
        lines = ["projects are the folders directly in the user's Shared Folder. a sandbox can mount several, each at "
                 "/workspace/<project>, and while it has one, no other instance can mount that one.",
                 self.common + " and " + self.engine + " are not projects: they are always mounted (" + self.engine
                 + " read-only), and no tool changes them."]
        if self.available():
            self.running()
            self.cleanup()                             # a crashed instance's container must not seem to hold anything
        names = self.projects_of_disk()
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
                    if self.readonly_of(name) is not None:
                        state += ", " + self.readonly_text(name)
                lines.append("- " + name + ": " + state)
        return "\n".join(lines) + "\n" + self.status_line()

    def create_project(self, name):
        """create_project: a new, empty folder Shared Folder/<name>"""
        with self.lock:
            problem = self.name_problem(name) or self.readonly_problem(name, "create")
            if problem:
                return problem
            for existing in os.listdir(self.shared_dir) if os.path.isdir(self.shared_dir) else []:
                if existing.lower() == name.lower():
                    return "'" + existing + "' exists already in Shared Folder: use it, or pick another name"
            os.makedirs(self.folder(name))
            return ("created project " + name + " (Shared Folder/" + name + "). mount_project mounts it, or open_sandbox "
                    "with projects=[\"" + name + "\"]\n" + self.status_line())

    def rename_project(self, name, new_name):
        """rename_project: rename a project folder nobody has mounted"""
        with self.lock:
            real, problem = self.find_project(name)
            if problem:
                return problem
            problem = (self.readonly_problem(real, "rename") or self.name_problem(new_name)
                       or self.readonly_problem(new_name, "create"))
            if problem:
                return problem
            for existing in os.listdir(self.shared_dir):
                if existing.lower() == new_name.lower() and existing != real:
                    return "'" + existing + "' exists already in Shared Folder: pick another name"
            if self.mounted(real):
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
            problem = self.readonly_problem(real, "delete")
            if problem:
                return problem
            if self.mounted(real):
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

    # --- terminals: shells that stay open between calls (classes/terminal.py) ---
    def terminals_text(self):
        """the open terminals and where each one is, e.g. "main (in /workspace/website)" """
        return ", ".join(name + " (in " + str(t.folder) + ")" for name, t in self.terminals.items() if t.alive())

    def terminal(self, command, name=None):
        """terminal: run a command in a shell that stays open (opened by the first call with this name). its folder
        (cd), variables, functions and activated environments stay for the next call"""
        name = str(name or "main").strip()
        if not re.fullmatch(TERMINAL_NAME, name):
            return "a terminal's name: letters, digits, - and _ only, at most 30 characters, e.g. main or server"
        if not isinstance(command, str) or not command.strip():
            return "give the command to run"
        if not self.running():
            return self.not_running()
        opened = ""
        with self.lock:                                # opening: one at a time, and not while the sandbox restarts
            terminal = self.terminals.get(name)
            if terminal and not terminal.alive():
                self.terminals.pop(name)
                terminal = None
            if not terminal:
                if len(self.terminals) >= TERMINALS:
                    return ("already " + str(TERMINALS) + " terminals are open: " + self.terminals_text()
                            + ". use one of them, or close_terminal one first")
                shell = ["bash", "--noprofile", "--norc", "--noediting", "-i"]   # -i: see classes/terminal.py
                terminal = Terminal(name, [self.command, "exec", "-i", "--workdir", self.workdir(), self.container]
                                    + shell, [self.command, "exec", self.container])
                problem = terminal.start()
                if problem:
                    return problem
                self.terminals[name] = terminal
                opened = "(opened a new terminal '" + name + "' in " + str(terminal.folder) + ")\n"
        text, code, note = terminal.run(command, self.timeout)
        text = text.strip("\n")
        if note == "ended" or note == "timeout_reset":
            with self.lock:
                if self.terminals.get(name) is terminal:
                    self.terminals.pop(name)
        if note is None:
            answer = text or "(no output)"
            if code:
                answer += "\n(exit code " + str(code) + ")"
        elif note == "timeout":
            answer = ((text + "\n") if text else "") + ("error: stopped after " + str(self.timeout) + " seconds "
                      "(like ctrl+c). the terminal is still open: its folder and variables are kept")
        elif note == "timeout_reset":
            answer = ((text + "\n") if text else "") + ("error: stopped after " + str(self.timeout) + " seconds, "
                      "and it didn't end, so the terminal '" + name + "' was closed. its folder and variables are "
                      "gone; the next call opens a new one")
        else:
            answer = ((text + "\n") if text else "") + ("the terminal '" + name + "' ended (exit, `set -e` and a "
                      "failing command, or the sandbox stopped). its folder and variables are gone; the next call "
                      "opens a new one")
        if terminal.alive():
            answer += "\n[terminal " + name + ", now in " + str(terminal.folder) + "]"
        return opened + answer

    def close_terminal(self, name=None):
        """close_terminal: close one terminal, or all of them (no name)"""
        with self.lock:
            if not self.terminals:
                return "no terminal is open"
            if name:
                terminal = self.terminals.pop(str(name).strip(), None)
                if not terminal:
                    return "no terminal called '" + str(name) + "'. open: " + (self.terminals_text() or "none")
                closing = [terminal]
            else:
                closing = list(self.terminals.values())
                self.terminals.clear()
        for terminal in closing:                       # outside the lock: closing a busy one takes a few seconds
            terminal.close()
        names = ", ".join(t.name for t in closing)
        return ("closed " + names + ". programs it started in the background keep running\n" + self.status_line())

    # --- your /sandbox commands (main.py) ---
    def overview(self):
        """/sandbox: what runs here, and every sandbox"""
        if not self.available():
            return self.command + " is not installed or not running, so there are no sandboxes right now"
        here = self.running()
        self.cleanup()
        lines = [self.status_line()]
        if self.view_url():
            lines.append("view: open " + self.view_url() + " in your browser to watch (and take over)")
        lines.append("sandboxes:")
        for name, problem in self.sandboxes().items():
            marks = ""
            if name == here:
                marks += " (running here)"
            others = 0 if problem else self.others_running(name)
            if others:
                marks += " (running in " + str(others) + " other instance(s))"
            if problem:
                marks += " (" + problem + ")"
            else:
                if not self.built_at(name):
                    marks += " (not built yet)"
                if os.path.isfile(os.path.join(self.sandboxes_dir, name, SETTINGS)):
                    marks += " [" + self.describe_settings(self.settings(name)[0], short=True) + "]"
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
                              "inside it is gone, open notebooks and terminals are closed; the files in Shared Folder "
                              "stay.")
            return "stopped " + here
