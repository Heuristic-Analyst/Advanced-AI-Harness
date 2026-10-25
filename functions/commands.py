# commands.py — what you type is either a message for the model, or a command for the program.
# a command starts with "/". this file decides which one it is and checks it is typed the right way,
# so main.py only has to act on the answer.

COMMANDS = {                                         # every command, with what it does. the help list is made from
    "/new": "start a new conversation (the current one stays saved)",   # this, so a new command only needs
    "/list": "show the saved conversations",                            # one new line here (and one in main.py)
    "/open <name>": "continue a saved conversation",                    # <name> = any one word
    "/rename <old> <new>": "rename a saved conversation",               # on|off = one of these words
    "/delete <name>": "delete a conversation, with everything in it",   # a command may have several forms:
    "/sandbox": "this instance's sandbox (project, network, notebooks), and all sandboxes",   # one line each
    "/sandbox net on|off": "switch the sandbox's internet on or off (off whenever the agent opens one)",
    "/sandbox shell": "a root shell inside the sandbox, for you. type exit to come back",
    "/sandbox close": "stop the sandbox. its project is free for other instances again",
    "/help": "show this list",
    "/exit": "leave the program",
    "/quit": "leave the program (the same as /exit)",
}


def help_text():
    """the list of all commands, one per line"""
    lines = ["commands:"]
    for command, what in COMMANDS.items():
        lines.append("  " + command.ljust(22) + what)   # ljust(22): fill up to 22 characters, so the texts line up
    return "\n".join(lines)


def forms(command):
    """every way a command may be typed, e.g. ["/open <name>"] for "/open". empty if there is no such command"""
    return [written for written in COMMANDS if written.split()[0] == command]   # "/open <name>" -> "/open"


def fits(words, written):
    """do the typed words fit this form? <x> = any word, a|b = one of these words, anything else = exactly it"""
    parts = written.split()
    if len(words) != len(parts):                     # as many words as the form has? "/open <name>" = 2
        return False
    for word, part in zip(words[1:], parts[1:]):
        if not part.startswith("<") and word not in part.split("|"):
            return False
    return True


def check_input(text):
    """look at what the user typed (already stripped) and say what to do with it:
    "skip"     nothing to do: an empty line, or a command that was already handled here (/help, an unknown one,
               a command typed the wrong way)
    "exit"     leave the program
    "message"  not a command: send it to the model
    "new", "list", "open", "rename", "delete", "sandbox"   that command, typed right: main.py does it"""
    if text == "":                                   # just pressed enter
        return "skip"
    if not text.startswith("/"):                     # no "/" in front: a normal message
        return "message"

    words = text.split()                             # "/rename a b" -> ["/rename", "a", "b"]
    command = words[0]
    written = forms(command)
    if not written:                                  # starts with "/", but we don't know it
        print("command not found: " + command)
        print(help_text())
        return "skip"
    if command in ("/exit", "/quit"):                # these may have words after them: "/exit now" leaves too
        return "exit"
    if not any(fits(words, form) for form in written):   # CHECK: typed like one of its forms?
        print("usage: " + "  or  ".join(written))
        return "skip"
    if command == "/help":
        print(help_text())
        return "skip"                                # handled: nothing more to do
    return command[1:]                               # "/open" -> "open": main.py does the rest
