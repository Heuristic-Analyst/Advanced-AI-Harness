# locks.py — "in use" signs between several running copies of this program ("instances"). you can start main.py
# more than once; each instance has its own sandbox, and these locks make sure two of them never mount the same project
# or run the same notebook at the same time.
#
# how: a lock is a file in Locks/. holding it = keeping that file open, with a lock from the operating system on it.
# the operating system takes that lock away by itself when the program ends, HOWEVER it ends: /exit, a crash, a closed
# terminal, a killed process, a power cut. so a forgotten lock can't exist. what counts is only that OS lock, never
# whether a file is there.
# no files pile up either: an instance deletes its own lock files when it gives a lock back, and at every start the
# files nobody holds (the leftovers of crashed instances) are deleted.
#
# the locks this program uses:
#   instance-<id>          held as long as that instance runs: how the others know it is alive
#   project-<name>         held while this instance's sandbox has that project mounted
#   notebook-<hash>        held while a notebook is open in this instance's sandbox
# the same idea as the original AI-Harness (locks.py there).

import os
import time
import threading
from config import LOCKS_DIR, INSTANCE

if os.name == "nt":                                  # windows locks files one way, mac and linux another
    import msvcrt
else:
    import fcntl

held = {}                                            # lock name -> its open file: the locks THIS instance holds
guard = threading.Lock()                             # tools run in parallel threads: one changes `held` at a time


def file_of(name):
    return os.path.join(LOCKS_DIR, name + ".lock")


def os_lock(f):
    """try to put the operating system's lock on this open file. True = got it, False = another program has it.
    never waits"""
    try:
        f.seek(0)
        if os.name == "nt":
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def let_go(f):
    """take the OS lock off the file, and close it"""
    try:
        f.seek(0)
        if os.name == "nt":
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    f.close()


def same_file(f, path):
    """is the open file f still the file at path? not if its holder deleted it while we were opening it"""
    try:
        now = os.stat(path)
    except OSError:
        return False
    mine = os.fstat(f.fileno())
    return now.st_ino == mine.st_ino and now.st_dev == mine.st_dev


def drop(f, name):
    """delete the lock's file, then let go of it. in this order, so nobody can take a file that is about to go"""
    try:
        os.remove(file_of(name))
    except OSError:                                  # windows can't delete an open file: tried once more below
        pass
    let_go(f)
    if os.name == "nt" and os.path.exists(file_of(name)):
        try:
            os.remove(file_of(name))
        except OSError:                              # another program has it open right now: it stays, harmless
            pass


def take(name):
    """take the lock. True = this instance holds it now (or held it already). False = another instance holds it"""
    with guard:
        if name in held:
            return True
        os.makedirs(LOCKS_DIR, exist_ok=True)
        while True:
            f = open(file_of(name), "a+")            # "a+" = open it, and create it if it isn't there yet
            if not os_lock(f):
                f.close()
                return False
            if same_file(f, file_of(name)):          # the normal case
                held[name] = f
                return True
            let_go(f)                                # its holder deleted it while we opened it: once more


def wait_take(name, seconds=5):
    """take the lock, waiting a few seconds if another instance has it. for locks held only for a moment"""
    give_up = time.time() + seconds
    while not take(name):
        if time.time() >= give_up:
            return False
        time.sleep(0.1)
    return True


def release(name):
    """give the lock back and delete its file. a lock this instance doesn't hold is left alone"""
    with guard:
        f = held.pop(name, None)
        if f:
            drop(f, name)


def is_free(name):
    """is nobody holding this lock right now? only looks, the lock is not kept. (a file nobody holds is a leftover of a
    crash, and is deleted on the way)"""
    with guard:
        if name in held:
            return False
    try:
        f = open(file_of(name), "r")                 # "r": only look, never create a file
    except FileNotFoundError:
        return True
    if not os_lock(f):                               # someone holds it
        f.close()
        return False
    if same_file(f, file_of(name)):                  # nobody had it: a leftover
        drop(f, name)
    else:
        let_go(f)
    return True


def alive(instance):
    """is the instance with this id still running? it is, as long as its instance lock is held"""
    if instance == INSTANCE:
        return True
    return not is_free("instance-" + instance)


def start():
    """at startup: take this instance's own lock, then delete the lock files nobody holds (leftovers of crashes)"""
    take("instance-" + INSTANCE)
    for file in sorted(os.listdir(LOCKS_DIR)):
        if file.endswith(".lock"):
            is_free(file[:-len(".lock")])            # deletes the file only if nobody holds it


def stop():
    """at exit: give back every lock of this instance, which deletes their files"""
    for name in list(held):                          # list(...) = a copy, because release changes `held`
        release(name)
