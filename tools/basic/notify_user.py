# tools/basic/notify_user.py — a sound on the USER'S computer (not in the sandbox), for when the agent stops before the
# task is done because it needs them: a captcha, a login, a question, the network switched on, a decision. the idea:
# you give it a task and look away; the sound says "come back, it's waiting for you". a task that simply finishes
# makes no sound.
#
# it plays your system's own notification sound, the first way that works on this computer:
#   windows   winsound (part of python)
#   mac       afplay with a sound from /System/Library/Sounds
#   linux     paplay / pw-play / canberra-gtk-play / aplay with a freedesktop or alsa sound
#   anything else, or none of those: the terminal bell (only heard in a terminal that has one switched on)
# your own sound instead: put its path into SOUND below (a .wav works everywhere; mac also .aiff/.mp3, linux .oga)

import os
import sys
import time
import shutil
import subprocess

SOUND = ""        # your own sound file, e.g. r"C:\Users\me\ding.wav" or "/home/me/ding.oga". "" = the system's own
REPEAT = 3        # how often it plays, a moment apart: once is easy to miss when you're not at the computer

MAC_SOUNDS = ["/System/Library/Sounds/Glass.aiff", "/System/Library/Sounds/Ping.aiff"]
LINUX_SOUNDS = ["/usr/share/sounds/freedesktop/stereo/message-new-instant.oga",
                "/usr/share/sounds/freedesktop/stereo/bell.oga",
                "/usr/share/sounds/freedesktop/stereo/complete.oga",
                "/usr/share/sounds/alsa/Front_Center.wav"]


def quiet(command):
    """start a player and don't wait for it: the agent goes on while it plays"""
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def player_for(path):
    """the command that plays this file on this computer, or None"""
    if sys.platform == "darwin":
        return ["afplay", path] if shutil.which("afplay") else None
    for player in ("paplay", "pw-play"):               # pulseaudio / pipewire: what most linux desktops have
        if shutil.which(player):
            return [player, path]
    if path.endswith(".wav") and shutil.which("aplay"):
        return ["aplay", "-q", path]
    return None


def play_once():
    """one sound. returns how it was played, or None when nothing could"""
    if sys.platform.startswith("win"):
        import winsound
        if SOUND and os.path.isfile(SOUND):
            winsound.PlaySound(SOUND, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return "winsound (" + SOUND + ")"
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)   # windows' own "something needs you" sound
        return "winsound"
    files = [SOUND] if SOUND else (MAC_SOUNDS if sys.platform == "darwin" else LINUX_SOUNDS)
    for path in files:
        if os.path.isfile(path):
            command = player_for(path)
            if command:
                quiet(command)
                return command[0] + " (" + path + ")"
    if sys.platform != "darwin" and shutil.which("canberra-gtk-play"):   # linux: the desktop theme's own sound by name
        quiet(["canberra-gtk-play", "-i", "message-new-instant"])
        return "canberra-gtk-play"
    terminal = sys.__stdout__                          # the real terminal (the window catches print, not this)
    if terminal and terminal.isatty():
        terminal.write("\a")
        terminal.flush()
        return "the terminal bell"
    return None


def run(agent, reason=""):
    how = None
    try:
        for i in range(REPEAT):
            if i:
                time.sleep(0.8)
            how = play_once() or how
    except Exception as e:                             # no sound card, a broken player: say so, never crash the turn
        return ("could not play a sound (" + type(e).__name__ + ": " + str(e) + "). say clearly in your reply what "
                "you need from the user")
    if not how:
        return ("no way to play a sound was found on the user's computer. say clearly in your reply what you need "
                "from the user")
    return ("a sound played on the user's computer (" + how + ")" + (" for: " + reason if reason else "")
            + ". now end your reply: say what you need from them, and wait for their answer")


TOOL = {
    "name": "notify_user",
    "description": "Play a sound on the user's computer, to call them back. The user gives you a task and looks away "
                   "until it is done. Use this ONLY when you have to stop BEFORE the task is done because you need "
                   "them: a captcha or bot check, a login or code, the network switched on, a question or a decision "
                   "you can't make yourself, something missing, an error you can't get past. Call it, then end your "
                   "reply with what you need, and wait. Don't use it for a normal answer or a finished task, and only "
                   "once per stop.",
    "parameters": {"type": "object",
                   "properties": {"reason": {"type": "string",
                                             "description": "in a few words what you need, e.g. captcha on google"}}},
}
