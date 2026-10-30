# terminal.py — a shell that STAYS OPEN inside the sandbox, for the terminal tool (tools/sandbox/terminal.py).
#
# sandbox_shell starts a new bash for every command: open, run, close. so `cd`, `export X=1`, `source venv/bin/activate`
# or a shell function are gone with the next call. a terminal is ONE bash that keeps running inside the container
# between calls, like a terminal window you keep open: where it is (cd), its variables and functions stay.
#
# how it works:
#   - opening one starts `podman exec -i <container> bash -i` and keeps that program running. we write commands into its
#     input and read what it prints. no screen, no tty: it is bash reading commands from a pipe. -i (interactive) only
#     for one thing: ctrl+c (SIGINT) then drops the rest of the running command, like in a real terminal, instead of
#     ending bash. its prompts are switched off, and so is ! (history), so `echo "hi!"` stays what it is
#   - every command goes in wrapped: the command's text as a quoted heredoc (so quotes, $ and backticks reach bash
#     untouched), run with eval in the shell itself (so cd and variables stay), with its input from /dev/null (a
#     command waiting for keyboard input would hang forever, and would eat our next command). right after it, bash
#     prints a line with a random marker, the exit code and the folder it is in now. reading up to that line = done
#   - too slow (the time limit): only what THIS command started is stopped, like ctrl+c in a real terminal. bash itself,
#     its folder and variables survive, and so do programs an EARLIER command started in the background. how: before
#     each command bash writes down the time (/proc/uptime), and the stopper sends ctrl+c to bash and to every process
#     below it that started after that time, then kills those that ignore it. if even that doesn't end the command,
#     the whole terminal is stopped, and the next call opens a new one
#   - exit, or `set -e` and a failing command, ends the bash: the terminal is gone, the next call opens a new one
#   - the sandbox stops or restarts (close_sandbox, mount_project): its terminals end with it
#
# classes/sandbox.py owns the terminals (sandbox.terminals) and opens, uses and closes them. nothing here knows podman:
# the sandbox hands in the command that starts bash, and the one that runs a helper script next to it.

import os
import time
import secrets
import threading
import subprocess

CAP = 4_000_000                 # bytes of output kept per command. more: the start is dropped (the end matters most)
GRACE = 3                       # seconds a stopped command gets to end before it is killed, and bash to answer after

# runs inside the container, next to the terminal's bash: stop every process below bash ($1) that started after the
# time bash wrote down before the current command. $2: INT (ctrl+c, the first try: to them AND to bash, which then
# drops the rest of the command, like a real terminal), KILL (the second, only them), or ALL (it didn't end: bash too). only bash builtins (read, kill), so it works in a sandbox without ps or pkill
STOPPER = r'''
root=$1; how=$2
start=0; read -r start < "/tmp/.harness-terminal-$root.start" 2>/dev/null
declare -A parent began
for f in /proc/[0-9]*/stat; do
  read -r s < "$f" 2>/dev/null || continue
  pid=${s%% *}; rest=${s##*) }; set -- $rest      # after the name: state ppid ... (starttime is the 20th)
  parent[$pid]=$2; began[$pid]=${20}
done
found=(); todo=("$root")
while ((${#todo[@]})); do                         # walk down from bash, only through processes started by this command
  p=${todo[0]}; todo=("${todo[@]:1}")
  for c in "${!parent[@]}"; do
    if [[ ${parent[$c]} == "$p" ]] && (( ${began[$c]:-0} >= start )); then found+=("$c"); todo+=("$c"); fi
  done
done
if [[ $how == ALL ]]; then kill -KILL "${found[@]}" "$root" 2>/dev/null
elif [[ $how == INT ]]; then kill -INT "${found[@]}" "$root" 2>/dev/null    # bash too: it drops the rest of the line
elif ((${#found[@]})); then kill -"$how" "${found[@]}" 2>/dev/null; fi
echo "${#found[@]}"
'''


def split(marker):
    """the marker as two quoted halves for printf: what bash prints has it whole, the command we send never does. so
    even if bash echoed its input, the command can't be mistaken for the end of the output"""
    half = len(marker) // 2
    return "'" + marker[:half] + "' '" + marker[half:] + "'"


class Terminal:
    def __init__(self, name, start_argv, helper_argv, cwd=None):
        """name: e.g. "main". start_argv: the command that starts bash reading from its input (podman exec -i ...).
        helper_argv: the command that runs a bash script next to it, the script's arguments are added at the end"""
        self.name = name
        self.helper_argv = helper_argv
        self.folder = None                       # where it is now (after the last command)
        self.pid = None                          # bash's process number INSIDE the container, for the stopper
        self.lock = threading.Lock()             # one command at a time per terminal
        self.data = bytearray()                  # what it printed since the current command began
        self.dropped = 0                         # bytes of that dropped from the start (more than CAP)
        self.ended = False                       # bash ended (exit, the sandbox stopped, ...)
        self.changed = threading.Condition()     # the reader tells the waiting command: new output, or ended
        self.process = subprocess.Popen(start_argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, bufsize=0, cwd=cwd)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        """the whole time it runs: move what bash prints into self.data"""
        out = self.process.stdout.fileno()
        while True:
            try:
                piece = os.read(out, 65536)
            except OSError:
                piece = b""
            with self.changed:
                if not piece:
                    self.ended = True
                    self.changed.notify_all()
                    return
                self.data += piece
                if len(self.data) > CAP:
                    cut = len(self.data) - CAP
                    del self.data[:cut]
                    self.dropped += cut
                self.changed.notify_all()

    def _write(self, text):
        try:
            self.process.stdin.write(text.encode("utf-8"))
            self.process.stdin.flush()
            return True
        except (OSError, ValueError):            # bash is gone
            return False

    def _wait_for(self, marker, until):
        """wait until the marker's line is printed, bash ended, or the time is up. returns the marker line's position
        in self.data, or None"""
        with self.changed:
            while True:
                at = self.data.find(marker)
                if at >= 0 and self.data.find(b"\n", at) >= 0:
                    return at
                if self.ended:
                    return None
                left = until - time.time()
                if left <= 0:
                    return None
                self.changed.wait(min(left, 1.0))

    def start(self):
        """wait until bash answers, and learn its process number. None if it runs, otherwise why not"""
        marker = "__HARNESS_TERMINAL_" + secrets.token_hex(8) + "__"
        self._write("exec 2>&1\n"
                    "set +H +o history; unset HISTFILE; PS1=''; PS2=''; PS0=''; PROMPT_COMMAND=''\n"   # quiet, and
                    "printf '%s%s %s %s\\n' " + split(marker) + " \"$$\" \"$PWD\"\n")             # ! stays a !
        at = self._wait_for(marker.encode(), time.time() + 30)
        if at is None:
            text = self.data.decode("utf-8", "replace").strip()
            self.close()
            return "the terminal did not start" + (": " + text[-800:] if text else "")
        line = self.data[at:self.data.find(b"\n", at)].decode("utf-8", "replace").split(" ", 2)
        self.pid, self.folder = line[1], line[2] if len(line) > 2 else None
        with self.changed:
            self.data.clear()
        return None

    def alive(self):
        return not self.ended and self.process.poll() is None

    def stop_command(self, how):
        """run the stopper next to bash (see STOPPER). returns how many processes it hit, or None if it couldn't run"""
        try:
            done = subprocess.run(self.helper_argv + ["bash", "-c", STOPPER, "stopper", str(self.pid), how],
                                  capture_output=True, text=True, timeout=60)
            return int(done.stdout.strip() or 0)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None

    def run(self, command, timeout):
        """run one command in this terminal. returns (what it printed, the exit code or None, a note or None)"""
        with self.lock:
            if not self.alive():
                return "", None, "ended"
            marker = "__HARNESS_DONE_" + secrets.token_hex(8) + "__"
            end = "__HARNESS_END_" + secrets.token_hex(8) + "__"
            with self.changed:
                self.data.clear()                # anything printed between commands (a background job) is dropped:
                self.dropped = 0                 # it can't be told apart from this command's output anyway
            wrapped = ("read -r __hs_t _ < /proc/uptime; printf '%s\\n' \"${__hs_t/./}\" > /tmp/.harness-terminal-$$.start 2>/dev/null\n"
                       "IFS= read -r -d '' __hs_c <<'" + end + "' || true\n"
                       + command.rstrip("\n") + "\n" + end + "\n"
                       "eval \"$__hs_c\" < /dev/null\n"
                       "printf '\\n%s%s %s %s\\n' " + split(marker) + " \"$?\" \"$PWD\"\n")
            if not self._write(wrapped):
                return "", None, "ended"
            note = None
            at = self._wait_for(marker.encode(), time.time() + timeout)
            if at is None and not self.ended:    # too slow: ctrl+c for what this command started, then kill
                note = "timeout"
                for how in ("INT", "KILL", "KILL"):
                    self.stop_command(how)
                    at = self._wait_for(marker.encode(), time.time() + GRACE)
                    if at is not None or self.ended:
                        break
                if at is None and not self.ended:    # it goes on (a loop in bash itself): the whole terminal ends
                    self.stop_command("ALL")
                    self._wait_for(b"\0never\0", time.time() + GRACE)
                    note = "timeout_reset"
            with self.changed:
                if at is None:                   # bash ended: everything it printed until then
                    text = self.data.decode("utf-8", "replace")
                    code = None
                    if note is None:
                        note = "ended"
                else:
                    text = self.data[:at].decode("utf-8", "replace")
                    line = self.data[at:self.data.find(b"\n", at)].decode("utf-8", "replace").split(" ", 2)
                    code = int(line[1]) if len(line) > 1 and line[1].lstrip("-").isdigit() else None
                    self.folder = line[2] if len(line) > 2 else self.folder
                dropped = self.dropped
                self.data.clear()
            if text.endswith("\n"):              # the newline put in front of the marker line
                text = text[:-1]
            if dropped:
                text = "(the first " + str(dropped) + " bytes of the output were dropped)\n" + text
            if note == "timeout_reset" or (note is None and not self.alive()):
                self.close()
            return text, code, note

    def close(self):
        """end bash: its input closes (bash ends after the command it is running), or it is killed"""
        if self.process.poll() is None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                if self.pid:
                    self.stop_command("ALL")
                self.process.kill()
                try:
                    self.process.wait(5)
                except subprocess.TimeoutExpired:
                    pass
        self.ended = True
