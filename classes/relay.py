# relay.py — the Relay: a door from YOUR computer into the sandbox, for "view" in a sandbox's sandbox.json.
#
# a program inside the sandbox (e.g. the browser kit's screen, port 6080) listens on the sandbox's own 127.0.0.1, which
# your computer can't reach. the relay listens on your computer's 127.0.0.1, on a free port, and carries every
# connection into the sandbox through its own `podman exec -i ... python3`:
#
#   your browser -> 127.0.0.1:<free port> (your computer) -> podman exec -i -> 127.0.0.1:<view port> (the sandbox)
#
# why this way, and not podman's own port publishing (-p):
#   - it works with the sandbox's network OFF, and on Linux, Mac and Windows alike: it needs nothing but `podman exec`
#   - nothing inside the sandbox is reachable from any network, not even from other containers: only through podman,
#     and only from your own computer (127.0.0.1)
#
# one relay per instance, made the first time a sandbox with "view" starts. its port stays the same for the whole
# run, also when the sandbox restarts (mount_project) or another one is opened, so a page you have open reconnects.
# needs python3 inside the sandbox.

import socket
import threading
import subprocess

# what runs inside the sandbox for one connection: its stdin goes to the port, what the port answers goes to its stdout
BRIDGE = r"""
import os, socket, sys, threading
s = socket.create_connection(("127.0.0.1", int(sys.argv[1])))
def up():
    while True:
        data = os.read(0, 65536)
        if not data:
            break
        s.sendall(data)
    try:
        s.shutdown(socket.SHUT_WR)
    except OSError:
        pass
threading.Thread(target=up, daemon=True).start()
out = sys.stdout.buffer
while True:
    data = s.recv(65536)
    if not data:
        break
    out.write(data)
    out.flush()
"""


class Relay:
    def __init__(self, command="podman"):
        self.command = command                 # "podman"
        self.container = None                  # where connections go now. None = nowhere (no sandbox with "view" runs)
        self.port = None                       # the port inside the sandbox
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))     # 127.0.0.1: only your own computer. 0: any free port
        self.server.listen(32)
        self.host_port = self.server.getsockname()[1]
        self.processes = set()                 # the running podman exec's, to stop them when the relay closes
        self.guard = threading.Lock()
        self.closed = False
        threading.Thread(target=self.accept, daemon=True).start()

    def point(self, container, port):
        """send new connections to this container's port. (None, None): to nowhere"""
        self.container, self.port = container, port

    def url(self):
        """the address for your browser, or None while no sandbox with "view" runs"""
        return "http://127.0.0.1:" + str(self.host_port) if self.container else None

    def accept(self):
        while not self.closed:
            try:
                conn, _ = self.server.accept()
            except OSError:                    # the server was closed
                return
            threading.Thread(target=self.carry, args=(conn,), daemon=True).start()

    def carry(self, conn):
        """one connection: a podman exec inside the sandbox, and two pumps, one per direction"""
        container, port = self.container, self.port
        if not container:
            conn.close()
            return
        try:
            process = subprocess.Popen([self.command, "exec", "-i", container, "python3", "-I", "-c", BRIDGE, str(port)],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       bufsize=0)
        except OSError:                        # podman is gone
            conn.close()
            return
        with self.guard:
            self.processes.add(process)

        def down():                            # the sandbox -> your browser
            try:
                while True:
                    data = process.stdout.read(65536)
                    if not data:
                        break
                    conn.sendall(data)
            except OSError:
                pass
            try:
                conn.shutdown(socket.SHUT_WR)
            except OSError:
                pass

        pump = threading.Thread(target=down, daemon=True)
        pump.start()
        try:                                   # your browser -> the sandbox
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                process.stdin.write(data)
        except (OSError, ValueError):
            pass
        try:
            process.stdin.close()              # the other side sees the end, and closes its side too
        except OSError:
            pass
        pump.join(timeout=30)
        if process.poll() is None:
            process.kill()
        process.wait()
        conn.close()
        with self.guard:
            self.processes.discard(process)

    def close(self):
        """at exit: stop listening, and end every open connection"""
        self.closed = True
        self.container = None
        try:
            self.server.shutdown(socket.SHUT_RDWR)     # wakes the waiting accept(): close() alone would leave the port
        except OSError:                                # listening as long as that thread waits
            pass
        try:
            self.server.close()
        except OSError:
            pass
        with self.guard:
            for process in list(self.processes):
                if process.poll() is None:
                    process.kill()
