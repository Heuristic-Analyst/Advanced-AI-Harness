# run it:  python main.py
# then type your messages. /help shows the commands, /exit (or ctrl+c) leaves.
# every conversation is saved in Conversations/<name>/state.json after every message, and every message
# is written into Conversations/<name>/log.jsonl (functions/conversations.py)
# the sandbox (classes/sandbox.py) belongs to this running program, not to a conversation: one for the whole run,
# handed to every agent. it is stopped when you leave, however you leave.

import atexit
from config import *
from classes.agent import Agent
from classes.sandbox import Sandbox
from functions.commands import check_input
from functions.read_text import read_text
from functions.load_tools import load_tools
from functions.load_skills import load_skills
from functions import conversations
from functions import locks

SANDBOX_TOOLS = ("sandbox", "notebook")              # tool folders (in tools/) and skills that need podman


def new_agent(name, messages=None):
    """a fresh agent for the conversation called name: it logs into that conversation's log.jsonl, saves long
    tool results into its results/ folder, and its checkpoint as checkpoint.md. messages: a saved conversation to go on
    with (it gets a new system prompt, with the checkpoint in it if there is one). every agent gets the same sandbox"""
    return Agent(MODEL, API_KEY, instructions=soul, stream=STREAM,      # by name: can never land
                 effort=EFFORT, print_thinking=PRINT_THINKING,        # in the wrong parameter
                 tools=tools, skills=skills, conversation=messages,
                 log_file=conversations.log_of(name), results_dir=conversations.results_of(name),
                 checkpoint_file=conversations.checkpoint_of(name), context_limit=CONTEXT_LIMIT,
                 sandbox=workspace)


def sandbox_command(words):
    """/sandbox, /sandbox net on|off, /sandbox shell, /sandbox close. words: what you typed, already checked"""
    if not workspace:
        print(CONTAINER_CMD + " was not found when the program started, so there are no sandboxes. "
              "install it (mac/windows: podman machine start), then start the program again")
    elif len(words) == 1:
        print(sandbox.overview())
    elif words[1] == "net":
        print(sandbox.user_network(words[2] == "on"))
    elif words[1] == "shell":
        print(sandbox.shell())
    elif words[1] == "close":
        print(sandbox.user_close())


def list_conversations(current):
    """print every saved conversation. * marks the one you are in"""
    saved = conversations.names()
    for name in saved:
        print(("* " if name == current else "  ") + name)
    if current not in saved:                         # the current one isn't saved yet: nothing was said in it
        print("* " + current + " (nothing said yet, not saved)")


if __name__ == "__main__":                           # runs only when you start main.py directly
    soul = read_text(SOUL_FILE) or "You are a helpful assistant."   # missing or empty file: a short fallback
    tools = load_tools(TOOLS_DIR)                    # every tool in tools/: name -> its schema and its function
    skills = load_skills(SKILLS_DIR)                 # every skill in skills/: name -> its description and its file

    locks.start()                                    # this instance's own lock: the others see that it runs
    atexit.register(locks.stop)                      # runs LAST (atexit goes backwards): every lock is given back
    sandbox = Sandbox(SANDBOXES_DIR, SHARED_DIR, COMMON, ENGINE, INSTANCE, command=CONTAINER_CMD,
                      memory=SANDBOX_MEMORY, cpus=SANDBOX_CPUS, pids=SANDBOX_PIDS, timeout=COMMAND_TIMEOUT)
    atexit.register(sandbox.shutdown)                # whatever happens (also a crash in python), the sandbox is stopped
    if sandbox.available():
        workspace = sandbox                          # the agents get it
        sandbox.cleanup()                            # containers left over by crashed instances are removed first
    else:                                            # no podman: the sandbox and notebook tools could do nothing,
        workspace = None                             # so the model doesn't get them, nor the skills for them
        for name in [n for n, tool in tools.items() if tool["folder"].split("/")[0] in SANDBOX_TOOLS]:
            tools.pop(name)
        for name in SANDBOX_TOOLS:
            skills.pop(name, None)
        print(CONTAINER_CMD + " not found or not running: no sandboxes, so the agent can't run code "
              "(mac/windows: podman machine start, then start this program again)")
    if not skills:                                   # no skills: load_skill could do nothing, so the model
        tools.pop("load_skill", None)                # doesn't get it. (None: no error if it isn't there either)

    current = conversations.new_name()               # the name of the conversation (folder) you are in: a new one at every start
    agent = new_agent(current)
    print("model: " + MODEL + " | tools: " + (", ".join(tools) or "none")
          + " | skills: " + (", ".join(skills) or "none")
          + " | sandboxes: " + ((", ".join(sandbox.names()) or "none") if workspace else "none"))
    print("conversation: " + current + "   (/help for commands)")

    try:
        while True:                                  # one round = one input from you
            text = input("\n> ").strip()             # strip: no spaces or empty lines around it
            what = check_input(text)                 # what to do with it (see functions/commands.py)
            words = text.split()                     # for the commands: ["/rename", "old", "new"]

            if what == "exit":
                break                                # leave the loop: the program ends below

            elif what == "new":
                current = conversations.new_name()   # the one you leave is saved already (after every message)
                agent = new_agent(current)
                print("new conversation: " + current)

            elif what == "list":
                list_conversations(current)

            elif what == "open":
                name = words[1]
                if name not in conversations.names():
                    print("no saved conversation called '" + name + "'. /list shows them")
                else:
                    data = conversations.load(name)
                    count = len(data["messages"])         # counted now: the agent adds its system prompt in front
                    agent = new_agent(name, data["messages"])   # the saved messages + a fresh system prompt
                    agent.tokens = data.get("tokens", 0)  # its size as of its last answer
                    current = name
                    print("opened " + name + ": " + str(count) + " messages")

            elif what == "rename":
                old, new = words[1], words[2]
                problem = conversations.rename(old, new)
                if problem:
                    print(problem)
                else:
                    if old == current:               # you renamed the one you are in: it is saved under the
                        current = new                # new name from now on: its log and results are in the new folder
                        agent.log_file = conversations.log_of(new)
                        agent.results_dir = conversations.results_of(new)
                        agent.checkpoint_file = conversations.checkpoint_of(new)
                    print("renamed " + old + " -> " + new)

            elif what == "delete":
                name = words[1]
                if not conversations.exists(name):
                    print("no conversation called '" + name + "'. /list shows them")
                elif input("delete '" + name + "' with everything in it? there is no undo. type yes: ").strip() != "yes":
                    print("not deleted")
                else:
                    problem = conversations.delete(name)
                    if problem:
                        print(problem)
                    else:
                        print("deleted " + name)
                        if name == current:          # you deleted the one you are in: start a new one, or the
                            current = conversations.new_name()   # next message would bring it back
                            agent = new_agent(current)
                            print("new conversation: " + current)

            elif what == "sandbox":
                sandbox_command(words)

            elif what == "message":
                notes = workspace.take_notes() if workspace else []   # what you changed with /sandbox meanwhile
                if notes:                            # (network, closed): the model is told with this message
                    text = "\n".join(notes) + "\n\n" + text
                try:
                    agent.ask(text)                  # ask prints the answer itself. the conversation remembers
                                                     # every round, so the model knows what was said before
                except Exception as e:               # the model or the connection failed: say what happened,
                                                     # then go on chatting. \n first: a stream may have
                                                     # stopped in the middle of a line
                    print("\nerror: " + type(e).__name__ + ": " + str(e))
                conversations.save(current, agent)   # after every message, also a failed one: tools that already
                                                     # ran are part of the conversation now

            # what == "skip": nothing to do, just ask for the next input
    except (KeyboardInterrupt, EOFError):            # ctrl+c, or ctrl+d / the input ended: leave quietly
        print()

    sandbox.shutdown()                               # stop this instance's sandbox: its project is free again
    locks.stop()                                     # (atexit would do both too: this way you see it happen)
    print("bye")
