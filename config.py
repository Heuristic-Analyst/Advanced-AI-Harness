import os
import datetime
from functions.read_json import read_json
from functions.environment import read_key

# Paths
HERE = os.path.dirname(os.path.abspath(__file__))   # the folder this file lives in. .env is found from here
ENV_FILE = os.path.join(HERE, ".env")
MODEL_FILE = os.path.join(HERE, "settings", "model.json")
SOUL_FILE = os.path.join(HERE, "Ego", "SOUL.md")     # who the agent is: the start of its system prompt. you write it
TOOLS_DIR = os.path.join(HERE, "tools")              # tools/<name>.py = one tool each (see functions/load_tools.py)
SKILLS_DIR = os.path.join(HERE, "skills")            # skills/<name>/SKILL.md = one skill each (see functions/load_skills.py)
CONVERSATIONS_DIR = os.path.join(HERE, "Conversations")   # Conversations/<name>/state.json = one conversation each
                                                          # (see functions/conversations.py). created with the first one
SANDBOXES_DIR = os.path.join(HERE, "Sandboxes")      # Sandboxes/<name>/Containerfile = one sandbox each (classes/sandbox.py)
SHARED_DIR = os.path.join(HERE, "Shared Folder")     # the ONLY folder of your computer a sandbox sees parts of:
COMMON = "Common"                                    #   Shared Folder/Common: mounted in every sandbox, always
ENGINE = "Notebook_Engine"                           #   Shared Folder/Notebook_Engine: the notebook engine, mounted read-only
                                                     #   Shared Folder/<project>: one project at a time, mounted by the agent
LOCKS_DIR = os.path.join(HERE, "Locks")              # "in use" signs of the running instances (functions/locks.py)

# This running main.py (an "instance"): its process number and when it started. you can run several at once, each
# with its own sandbox. the time keeps it unique: after a restart, another program may get the same process number
INSTANCE = str(os.getpid()) + "-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S")   # e.g. 48213-20261025161304

# Sandbox (see classes/sandbox.py). limits for a running sandbox, so a runaway script can't take your computer down
CONTAINER_CMD = "podman"   # the container program. podman is rootless: "root" inside the sandbox is just you outside
SANDBOX_MEMORY = "2g"      # memory a sandbox may use
SANDBOX_CPUS = "2"         # CPU cores a sandbox may use
SANDBOX_PIDS = 512         # processes a sandbox may have at once
COMMAND_TIMEOUT = 600      # seconds a command in the sandbox (sandbox_shell, a notebook call) may run, then it is stopped

# Model settings: read the file once, then take what we need from it
MODEL_SETTINGS = read_json(MODEL_FILE)
MODEL = MODEL_SETTINGS["Model"]                        # required: without a model nothing works
STREAM = MODEL_SETTINGS.get("Stream", False)           # optional: True = print the answer piece by piece as it arrives
EFFORT = MODEL_SETTINGS.get("Effort")                  # optional: how hard the model thinks ("low", "medium", "high").
                                                       # None = the model's own default
PRINT_THINKING = MODEL_SETTINGS.get("PrintThinking", False)   # optional: True = show the thinking too, not only the answer
CONTEXT_LIMIT = MODEL_SETTINGS.get("ContextLimit", 100_000)   # optional: tokens a conversation may have at most. keep it
                                                       # at or below your model's real limit. tokens, not characters:
                                                       # the model's window is counted in tokens

# Checkpoints (see tools/basic/checkpoint.py): when the conversation gets too full, the model writes down where it
# stands, and the conversation starts fresh with that checkpoint in its system prompt
CHECKPOINT_AT = 0.6        # a task ended above 60% of CONTEXT_LIMIT: the model writes its checkpoint
EMERGENCY_AT = 0.8         # above 80% in the middle of a task: the checkpoint is written right away, and the task
                           # goes on from it

# Long tool results (see functions/results.py). in characters, not tokens: the same for every model
RESULT_LIMIT = 8_000       # x: a tool result longer than this is saved into the conversation's results/ folder,
                           #    and the model only gets a short preview of it
RESULT_PART = 4_000        # y: a saved result is cut into parts of this size. read_result shows one part at a time
RESULT_PREVIEW = 300       # how many characters of the result's start, and of its end, are in the preview
if RESULT_PART > RESULT_LIMIT - 500:                   # a part (+ read_result's first line) must stay below the limit,
    raise SystemExit("config.py: RESULT_PART must be at least 500 smaller than RESULT_LIMIT")   # or reading a part
                                                       # would be too long again, and be saved again

# Provider name
provider = MODEL.split("/")[0].upper()               # "deepseek/deepseek-flash" -> "DEEPSEEK"

# API key for using the model from the provider
API_KEY = read_key(provider, ENV_FILE)
