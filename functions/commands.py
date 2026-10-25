# commands.py — what you type is either a message for the model, or a command for the program.
# a command starts with "/". this file decides which one it is and checks it has the right number of words,
# so main.py only has to act on the answer.

COMMANDS = {                                         # every command, with what it does. the help list is made from
    "/new": "start a new conversation (the current one stays saved)",   # this, so a new command only needs
    "/list": "show the saved conversations",                            # one new line here (and one in main.py)
    "/open <name>": "continue a saved conversation",
    "/rename <old> <new>": "rename a saved conversation",
    "/delete <name>": "delete a conversation, with everything in it",
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


def usage(command):
    """how a command is meant to be typed, e.g. "/open <name>" for "/open". None if there is no such command"""
    for written in COMMANDS:
        if written.split()[0] == command:            # "/open <name>" -> "/open"
            return written
    return None


def check_input(text):
    """look at what the user typed (already stripped) and say what to do with it:
    "skip"     nothing to do: an empty line, or a command that was already handled here (/help, an unknown one,
               a command with the wrong number of words)
    "exit"     leave the program
    "message"  not a command: send it to the model
    "new", "list", "open", "rename", "delete"   that command, with the right number of words: main.py does it"""
    if text == "":                                   # just pressed enter
        return "skip"
    if not text.startswith("/"):                     # no "/" in front: a normal message
        return "message"

    words = text.split()                             # "/rename a b" -> ["/rename", "a", "b"]
    command = words[0]
    written = usage(command)
    if written is None:                              # starts with "/", but we don't know it
        print("command not found: " + command)
        print(help_text())
        return "skip"
    if command in ("/exit", "/quit"):                # these may have words after them: "/exit now" leaves too
        return "exit"
    if len(words) != len(written.split()):           # CHECK: as many words as in its usage? "/open <name>" = 2
        print("usage: " + written)
        return "skip"
    if command == "/help":
        print(help_text())
        return "skip"                                # handled: nothing more to do
    return command[1:]                               # "/open" -> "open": main.py does the rest
