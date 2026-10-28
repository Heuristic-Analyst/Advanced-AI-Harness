#!/usr/bin/env python3
# browser.py — the browser kit's one command: `browser ...` inside the `browser` sandbox.
#
# a real Chromium, driven by agent-browser (github.com/vercel-labs/agent-browser): a small background program (the
# daemon) holds the browser, and every `browser <command>` is one short call to it. so the pages, tabs and logins live
# on between the agent's shell calls, until `browser stop`.
#
#   browser start [url]      open the browser, and the screen the user can watch (the "view" link in /sandbox)
#   browser stop             close it, and the screen
#   browser status           open or not, which page, which tabs
#   browser more [n]         the next part of a long answer (or part n)
#   browser <command> ...    everything agent-browser does: open <url>, snapshot -i, click @e3, fill @e5 "text",
#                            get text body, tab, back, screenshot, pdf <file>, ... (browser help: all of them)
#
# this folder is mounted READ-ONLY (Shared Folder/Browser): the agent can use the code but never change it. everything
# the browser writes goes into tmp/, the one folder in here it can write: the profile (logins), downloads, screenshots,
# logs. delete tmp/ any time the browser is closed, and it starts fresh.
#
# why one-shot calls: every sandbox_shell call is its own `podman exec`. a program it starts and keeps attached would
# die with the call or, worse, keep the call open until its time limit. so everything long-lived is started here
# detached (its own session, no shared output), and every call to agent-browser writes into a file, never a pipe.

import os
import re
import sys
import json
import time
import shutil
import signal
import tempfile
import subprocess

HERE = os.path.dirname(os.path.realpath(__file__))     # /workspace/Browser
TMP = os.path.join(HERE, "tmp")                        # the only folder in here that is writable
PROFILE = os.path.join(TMP, "profile")                 # chromium's profile: cookies, logins, history
DOWNLOADS = os.path.join(TMP, "downloads")
SHOTS = os.path.join(TMP, "shots")                     # screenshots without a path
FILES = os.path.join(TMP, "files")                     # a place for pdfs and other saved pages
LOGS = os.path.join(TMP, "logs")                       # what the screen and the browser print, for when something breaks
OUTPUT = os.path.join(TMP, "output.json")              # the last long answer, for `browser more`

AGENT_BROWSER = ["/opt/agent-browser/node_modules/.bin/agent-browser"]   # where the image puts it: outside the PATH, so
                                                       # it is only ever started through this file
CHROMIUMS = ["chromium", "chromium-browser", "google-chrome"]
DISPLAY = ":99"                                        # the screen chromium draws on
SCREEN = "1440x900x24"
NOVNC = "/usr/share/novnc"                             # the web page that shows the screen
VIEW_PORT = "6080"                                     # = "view" in Sandboxes/browser/sandbox.json
PAGE = 6000                                            # characters per answer. the harness saves anything over 8000
                                                       # as a "result" and shows only a preview: so stay below
TIMEOUT = 120                                          # seconds one call may take (agent-browser's own limit is 25 s)
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")           # terminal colours, in case some still come through

USAGE = """browser: a real Chromium for the agent (agent-browser), with a screen the user can watch.
  browser start [url]     open it              browser stop          close it
  browser status          what is open         browser more [n]      the rest of a long answer
  browser open <url>      go to a page         browser snapshot -i   what can be clicked or typed in, as @refs
  browser click @e3 | fill @e5 "text" | press Enter | get text body | tab | back | screenshot | pdf <file>"""


# --- small helpers ---
def say(text):
    print(text.rstrip())


def agent_browser():
    for path in AGENT_BROWSER:
        if os.path.isfile(path):
            return path
    return shutil.which("agent-browser")


def chromium():
    for name in CHROMIUMS:
        path = shutil.which(name)
        if path:
            return path
    return None


def processes():
    """every process in this sandbox: (pid, its command line as a list)"""
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        try:
            with open("/proc/" + entry + "/cmdline", "rb") as f:
                args = [a.decode("utf-8", "replace") for a in f.read().split(b"\0") if a]
        except OSError:
            continue
        if args:
            found.append((int(entry), args))
    return found


def named(args, *names):
    """is this command line one of these programs? (also when it runs through an interpreter: python3 websockify)"""
    return any(os.path.basename(a) in names for a in args[:2])


def browser_pids():
    """the chromium processes that use OUR profile"""
    return [pid for pid, args in processes()
            if any("chrom" in os.path.basename(a).lower() for a in args[:2]) and any(PROFILE in a for a in args)]


def pids_of(*names, needle=None):
    return [pid for pid, args in processes() if named(args, *names) and (needle is None or needle in args)]


def kill(pids, wait=5):
    """end these processes: politely first, then for good"""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in pids:
            try:
                os.kill(pid, sig)
            except OSError:
                pass
        give_up = time.time() + wait
        while time.time() < give_up and any(os.path.exists("/proc/" + str(p)) for p in pids):
            time.sleep(0.2)
        pids = [p for p in pids if os.path.exists("/proc/" + str(p))]
        if not pids:
            return


def environment():
    env = dict(os.environ)
    env.update({
        "DISPLAY": DISPLAY,
        "NO_COLOR": "1",
        "AGENT_BROWSER_EXECUTABLE_PATH": chromium() or "",
        "AGENT_BROWSER_PROFILE": PROFILE,               # a folder: cookies and logins are kept in it
        "AGENT_BROWSER_DOWNLOAD_PATH": DOWNLOADS,
        "AGENT_BROWSER_SCREENSHOT_DIR": SHOTS,
        "AGENT_BROWSER_IDLE_TIMEOUT_MS": "0",           # never close by itself: `browser stop` does
        "AGENT_BROWSER_ARGS": "--no-sandbox\n--window-size=1440,900\n--window-position=0,0",   # one per line.
                                                        # --no-sandbox: chromium's own sandbox can't work as root in a
                                                        # container; the container is the sandbox
    })
    return env


def call(args, timeout=TIMEOUT):
    """one call to agent-browser: (exit code, what it printed). its output goes into a file, never a pipe: if the call
    starts the daemon, the daemon keeps the file, and nothing waits for it to close"""
    with tempfile.TemporaryFile() as out:
        try:
            done = subprocess.run([agent_browser()] + args, stdin=subprocess.DEVNULL, stdout=out,
                                  stderr=subprocess.STDOUT, env=environment(), timeout=timeout,
                                  start_new_session=True)
            code, late = done.returncode, ""
        except subprocess.TimeoutExpired:
            code, late = 124, "\n(no answer after " + str(timeout) + " seconds: the call was stopped)"
        out.seek(0)
        text = ANSI.sub("", out.read().decode("utf-8", "replace")) + late
    return code, text.strip()


def spawn(command, log):
    """start a long-lived program, detached from this call: its own session, its output into tmp/logs/<log>.log"""
    with open(os.path.join(LOGS, log + ".log"), "ab") as f:
        subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, env=environment(),
                         start_new_session=True)


def prepare():
    """the folders in tmp/. None if all is well, otherwise what is wrong"""
    try:
        for folder in (PROFILE, DOWNLOADS, SHOTS, FILES, LOGS):
            os.makedirs(folder, exist_ok=True)
        probe = os.path.join(TMP, ".can-write")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except OSError as e:
        return ("can't write in " + TMP + " (" + str(e) + "). the Browser project must be mounted by the harness "
                "(mount_project Browser): it makes tmp/ the one writable folder in it")
    return None


def clear_locks():
    """chromium leaves "in use" files in its profile when it is killed (a sandbox that stopped). they would block the
    next start. only called while no chromium of ours runs; the Browser project is mounted by one instance at a time,
    so nobody else can be using the profile"""
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        path = os.path.join(PROFILE, name)
        if os.path.lexists(path):
            try:
                os.remove(path)
            except OSError:
                pass


# --- the screen: a virtual display, and a web page that shows it (noVNC) ---
def start_screen():
    """True if the screen runs (then the browser is drawn on it, and the user can watch)"""
    if not shutil.which("Xvfb"):
        return False
    socket_file = "/tmp/.X11-unix/X" + DISPLAY.lstrip(":")
    if not pids_of("Xvfb", needle=DISPLAY):
        if os.path.exists(socket_file):                # left by a display that is gone
            try:
                os.remove(socket_file)
                os.remove("/tmp/.X" + DISPLAY.lstrip(":") + "-lock")
            except OSError:
                pass
        spawn(["Xvfb", DISPLAY, "-screen", "0", SCREEN, "-nolisten", "tcp"], "xvfb")
        give_up = time.time() + 10
        while time.time() < give_up and not os.path.exists(socket_file):
            time.sleep(0.2)
    if not os.path.exists(socket_file):
        return False
    if shutil.which("fluxbox") and not pids_of("fluxbox"):          # a small window manager: windows get a frame
        spawn(["fluxbox"], "fluxbox")
    if shutil.which("x11vnc") and not pids_of("x11vnc"):            # the screen as VNC, only inside (127.0.0.1)
        spawn(["x11vnc", "-display", DISPLAY, "-localhost", "-rfbport", "5900", "-forever", "-shared", "-nopw",
               "-quiet"], "x11vnc")
    if shutil.which("websockify") and not pids_of("websockify"):    # VNC as a web page, also only inside. the user
        spawn(["websockify", "--web", NOVNC, "127.0.0.1:" + VIEW_PORT, "127.0.0.1:5900"], "novnc")   # gets there
    return True                                                     # through the harness ("view")


def stop_screen():
    kill(pids_of("websockify") + pids_of("x11vnc") + pids_of("fluxbox"))
    kill(pids_of("Xvfb", needle=DISPLAY))


# --- the commands ---
def missing():
    """None if this sandbox has what the browser needs, otherwise what is missing"""
    if not agent_browser() or not chromium():
        return ("this sandbox has no " + ("agent-browser" if not agent_browser() else "chromium") + ". the browser only "
                "works in the `browser` sandbox: close_sandbox, then open_sandbox browser with projects [\"Browser\", ...]")
    return None


def start(url=None):
    problem = missing() or prepare()
    if problem:
        say(problem)
        return 1
    if browser_pids():
        say("the browser is open already.\n" + status_text())
        return 0
    clear_locks()
    screen = start_screen()
    code, text = call((["--headed"] if screen else []) + ["open", url or "about:blank"])
    give_up = time.time() + 15
    while time.time() < give_up and not browser_pids():
        time.sleep(0.3)
    if not browser_pids():
        say("the browser did not start (exit code " + str(code) + "):\n" + text[-2000:]
            + "\nlogs: " + LOGS)
        return 1
    lines = ["the browser is open" + (" on a screen the user can watch: the \"view\" link (the user sees it with "
                                      "/sandbox, and it is in your status line)" if screen else
                                      " (no screen: nobody can watch it)") + ".",
             "profile (logins are kept): " + PROFILE + ". downloads: " + DOWNLOADS + "."]
    if url:
        lines.append(text)
        if re.search(r"ERR_INTERNET_DISCONNECTED|ERR_NAME_NOT_RESOLVED|ERR_NETWORK", text):
            lines.append("the page could not load: the sandbox's network is probably off. ask the user to switch it "
                         "on (/sandbox net on)")
    lines.append("next: browser open <url>, then browser snapshot -i. browser stop when done.")
    say("\n".join(lines))
    return 0


def stop():
    if missing():
        say(missing())
        return 1
    was_open = bool(browser_pids())
    if was_open:
        call(["close"], timeout=30)
        give_up = time.time() + 10
        while time.time() < give_up and browser_pids():
            time.sleep(0.3)
        kill(browser_pids())                           # it didn't close by itself: end it
    kill([pid for pid, args in processes()             # agent-browser's daemon: started again by the next start
          if any(os.path.basename(a).startswith("agent-browser") for a in args[:2])])
    stop_screen()
    clear_locks()
    say(("the browser is closed" if was_open else "the browser was not open") + ", and the screen is off. "
        "logins stay in " + PROFILE + " (delete " + TMP + " to forget them).")
    return 0


def status_text():
    if not browser_pids():
        return "the browser is not open. browser start [url] opens it."
    lines = ["the browser is open."]
    for label, args in (("page", ["get", "url"]), ("title", ["get", "title"]), ("tabs", ["tab"])):
        code, text = call(args, timeout=30)
        lines.append(label + ": " + (text if code == 0 else "(could not ask: " + text[-300:] + ")"))
    downloads = sorted(os.listdir(DOWNLOADS)) if os.path.isdir(DOWNLOADS) else []
    lines.append("downloads (" + DOWNLOADS + "): " + (", ".join(downloads[-10:]) or "none"))
    return "\n".join(lines)


def show(code, text):
    """print an answer. a long one is cut into parts of PAGE characters: the first is shown, the rest is kept for
    `browser more`"""
    text = text.strip() or "(no output)"
    if len(text) <= PAGE:
        say(text)
        return code
    parts = split(text)
    os.makedirs(TMP, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"parts": parts, "shown": 1}, f)
    say(parts[0] + "\n\n[part 1 of " + str(len(parts)) + " (" + str(len(text)) + " characters). the next part: "
        "browser more. tip: snapshot -i (only what can be clicked or typed in) and snapshot -s <css> (one part of the "
        "page) are much shorter]")
    return code


def split(text):
    """cut a long text into parts of at most PAGE characters, at line ends where possible"""
    parts, current = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > PAGE:                        # one very long line: cut it hard
            if current:
                parts.append(current)
                current = ""
            parts.append(line[:PAGE])
            line = line[PAGE:]
        if len(current) + len(line) > PAGE:
            parts.append(current)
            current = ""
        current += line
    if current:
        parts.append(current)
    return [p.rstrip("\n") for p in parts]


def more(which=None):
    try:
        with open(OUTPUT, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        say("there is no long answer to show more of")
        return 1
    parts = saved["parts"]
    if which is None:
        number = saved["shown"] + 1
    elif which.isdigit():
        number = int(which)
    else:
        say("browser more [n]: n is a part number")
        return 1
    if not 1 <= number <= len(parts):
        say("there are parts 1 to " + str(len(parts)) + (" (all shown)" if which is None else ""))
        return 1
    saved["shown"] = number
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(saved, f)
    footer = "browser more for the next" if number < len(parts) else "that was the last part"
    say(parts[number - 1] + "\n\n[part " + str(number) + " of " + str(len(parts)) + ": " + footer + "]")
    return 0


def main(args):
    if not args or args[0] in ("-h", "--help", "help"):
        if missing():
            say(missing())
            return 1
        say(USAGE + "\n\nagent-browser's own help (use its commands as browser <command>):\n")
        return show(*call(["--help"], timeout=30))
    command = args[0]
    if command == "start":
        return start(args[1] if len(args) > 1 else None)
    if command == "stop":
        return stop()
    if command == "status":
        problem = missing()
        say(problem or status_text())
        return 1 if problem else 0
    if command == "more":
        return more(args[1] if len(args) > 1 else None)
    problem = missing()
    if problem:
        say(problem)
        return 1
    if command in ("close", "quit", "exit"):           # agent-browser's own close would leave the screen running
        return stop()
    if not browser_pids():
        say("the browser is not open: browser start [url] first. (websites also need the sandbox's network: if the "
            "user hasn't switched it on, ask them for /sandbox net on)")
        return 1
    return show(*call(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
