# Advanced AI Harness, from scratch

A small AI assistant that runs in your terminal, built step by step so that every line is understood. It talks to any model through [LiteLLM](https://github.com/BerriAI/litellm), can use tools, loads skills when it needs them, saves every conversation, and keeps working when a conversation gets too long for the model. Everything it runs, it runs in a throwaway [Podman](https://podman.io) sandbox, never on your computer, including Jupyter notebooks.

## Features

- **Any model.** One line in `settings/model.json` picks it: DeepSeek, Anthropic, OpenAI, a local Ollama model, or anything else LiteLLM supports.
- **Streaming and thinking.** The answer is printed while it arrives, and the model's thinking can be shown or hidden.
- **Tools.** One Python file per tool in `tools/`, found automatically. Several tool calls in one answer run at the same time, and their results go back in the order the model asked.
- **Skills.** Step-by-step instructions in `skills/`. Only their names and one-line descriptions are in the system prompt; the model loads a skill's full text when a task matches it.
- **Conversations.** Every conversation is a folder, saved after every message. You can list, open, rename and delete them.
- **A log.** Every message ever said is written into the conversation's `log.jsonl`, and nothing in it is ever changed.
- **Long results.** A tool result that is too long is saved in parts. The model gets a preview, and reads or searches the rest (`read_result`, `search_result`).
- **Checkpoints.** When a conversation gets too full, the model writes down where it stands, and the conversation starts fresh from those notes.
- **Retries.** A busy or unreachable provider is tried again, waiting longer each time.
- **Sandboxes.** Code, installs and files happen in a rootless Podman container with no network (unless you switch it on), limits on memory, CPU and processes, and only three folders of your computer mounted, all `noexec`. The agent picks, opens and closes it itself.
- **Projects.** The agent works in `Shared Folder/Common`, which every sandbox sees, and in one project folder `Shared Folder/<project>` at a time, which it can create, mount, rename and delete with its tools.
- **Notebooks.** The agent creates, edits and runs real `.ipynb` notebooks inside the sandbox. Variables stay alive between cells, and every change is saved to the file at once, so you can open it any time.
- **Several at once.** You can run `main.py` more than once. Each one has its own sandbox, and locks make sure two of them never mount the same project or open the same notebook.

## How it fits together

- **`main.py`**: the chat loop. It reads what you type, sends `/commands` to `functions/commands.py`, and gives every other message to `agent.ask(text)`. After every message, also a failed one, it saves the conversation to `state.json`.
- **`classes/agent.py`**: the heart of the program. `ask()` is the loop: call the model, add its answer to the conversation, run the tools it asked for, and go again until it answers without tools. `call_model()` tries again on errors that may go away by themselves (3 times, after 1, 2 and 4 seconds). `show()` prints the answer while it streams in, then glues the pieces back into one finished answer.
- **The system prompt**: built fresh from four parts, always in this order: `Ego/SOUL.md`, the skills menu, `checkpoint.md`, the workspace (what runs in the sandbox). It is never saved in `state.json`, and only built when the context starts fresh (a new conversation, `/open`, a checkpoint), so the provider's prompt cache stays valid in between.
- **`classes/sandbox.py`**: the `Sandbox`, one for the whole run, handed to every agent (`agent.sandbox`). Everything that talks to Podman is in it: building and starting the container, sealing its network, running commands, mounting projects, finding and removing the leftovers of crashed instances. The tools in `tools/sandbox/` and `tools/notebook/` are thin: they call it.
- **`functions/locks.py`**: "in use" signs between running instances, held by the operating system, so a crash can never leave one behind.
- **Tools**: one file each in `tools/`, with `TOOL` (what the model sees) and `run(agent, **args)` (what the program does). They are found at the start, with no list to edit. All tool calls of one answer run at the same time, each in its own thread. Their results go back in the order the model asked, each with its call's id. Any problem comes back as a text starting with `error:`, so every call always gets an answer.
- **Skills**: only the name and description of each `SKILL.md` are in the system prompt. When a task matches, the model calls `load_skill` and gets the whole text back as a tool result. No skills: no `load_skill` either.
- **Long results**: a tool result longer than 8,000 characters is saved in 4,000-character parts as `results/results-<n>.json`. The model gets a preview with the start, the end and the number of parts. It reads one part with `read_result`, or finds lines with `search_result`, a grep with grep's options (`-E -i -w -v -A -B -o -c -m`). If a search answer is too long itself, it is saved as a new result.
- **Checkpoints**: the conversation's size comes from the token count the provider sends with every answer. A task that ended above 60% of `ContextLimit` gets a checkpoint request. Above 80% in the middle of a task, an emergency request comes right after the tool results. The model writes its notes in fixed sections (Goal, Decisions, Facts, Done, Failed, Open, Files, Last exchange) and gives them to the `checkpoint` tool. The tool saves `checkpoint.md`, empties the conversation, and builds the system prompt again with the checkpoint in it. The tool refuses when nobody asked, and the program asks at most twice per task.
- **Saving**: every conversation is a folder. `state.json` is what the model carries right now, written to a temporary file first and then swapped in. `log.jsonl` gets every message ever said, and the system prompt whenever it changed. It is only ever added to, and the program never reads it.
- **Safety**:
  - `calculate` only accepts digits and math symbols, and runs in its own isolated Python process (`-I`) that is stopped after 5 seconds.
  - Conversation, result and time zone names are checked against a pattern, so the model can never point the program at another folder or file.
  - The API key is read from `.env`, but never put into the environment.
  - Every command the model wants run goes into the sandbox. It sees only `Shared Folder/Common`, `Shared Folder/Notebook_Engine` (read-only) and one project, all mounted `noexec,nosuid,nodev`, with no network unless you switch it on.
  - Project and notebook names are checked too: `Common` and `Notebook_Engine` can never be created, renamed, deleted, mounted or unmounted, links to folders elsewhere are not projects, and a notebook can only live in `Common/` or the mounted project.

## Requirements

- Python 3.10 or newer
- An API key for your model provider (not needed for local models such as Ollama)
- [Podman](https://podman.io/docs/installation) for the sandboxes. On macOS or Windows, start its VM once with `podman machine start`. Without Podman everything else works, and the model simply doesn't get the sandbox and notebook tools.

## Quick start

```bash
git clone https://github.com/Heuristic-Analyst/AI-Harness-2-from-Scratch.git
cd AI-Harness-2-from-Scratch
pip install -r requirements.txt
```

Create a file called `.env` next to `main.py` with the key for your provider. The name is the provider part of the model, in capitals, followed by `_API_KEY`:

```
DEEPSEEK_API_KEY=sk-...
```

The key is only ever read from this file and passed to LiteLLM directly. It never goes into your environment variables, and `.gitignore` keeps it off GitHub.

Then:

```bash
python main.py
```

```
model: deepseek/deepseek-flash | tools: calculate, checkpoint, get_time, load_skill, nb_add, ..., sandbox_shell, search_result, unmount_project | skills: notebook, sandbox, stepwise-calculation | sandboxes: python, ubuntu
conversation: 20261024-01-10-05   (/help for commands)

> what is 17% of 2340?
```

## Commands

Anything that doesn't start with `/` is a message to the model.

| Command | What it does |
|---|---|
| `/new` | Start a new conversation. The current one stays saved. |
| `/list` | Show the saved conversations. `*` marks the one you are in. |
| `/open <name>` | Continue a saved conversation. |
| `/rename <old> <new>` | Rename a saved conversation, also the one you are in. |
| `/delete <name>` | Delete a conversation with everything in it. Asks first: type `yes`. |
| `/sandbox` | This instance's sandbox (project, network, open notebooks), and every sandbox: running here, in other instances, built or not. |
| `/sandbox net on\|off` | Switch the sandbox's internet on or off. It is off whenever the agent opens a sandbox; only you can switch it on. |
| `/sandbox shell` | A root shell inside the sandbox, for you. `exit` brings you back. |
| `/sandbox close` | Stop the sandbox. Its project is free for other instances again. |
| `/help` | Show the command list. |
| `/exit`, `/quit` | Leave. Ctrl+C or Ctrl+D leave too. Everything is saved already, and the sandbox is stopped. |

When you change the sandbox with `/sandbox net` or `/sandbox close`, the model is told with your next message (a line starting `[from the program, not the user]`), so it never works from an outdated picture.

## Settings

### `settings/model.json`

```json
{
  "Model": "deepseek/deepseek-flash",
  "Stream": true,
  "Effort": "high",
  "PrintThinking": true,
  "ContextLimit": 100000
}
```

| Setting | Meaning |
|---|---|
| `Model` | **Required.** Any LiteLLM model string: `provider/model`, e.g. `anthropic/...`, `openai/...`, `ollama/llama3`. |
| `Stream` | `true` = the answer is printed piece by piece while it arrives. Default `false`. |
| `Effort` | How hard the model thinks: `low`, `medium`, `high` (DeepSeek: `low`, `high`, `max`). Left out = the model's own default. A model that can't think simply ignores it. |
| `PrintThinking` | `true` = the model's thinking is shown too, not only its answer. It is always kept in the conversation and the log. Default `false`. |
| `ContextLimit` | Tokens a conversation may have at most. **Set it to your model's real context window, or below.** Default 100,000. |

### `config.py`

| Setting | Default | Meaning |
|---|---|---|
| `CHECKPOINT_AT` | `0.6` | A task ended above this share of `ContextLimit`: the model writes its checkpoint. |
| `EMERGENCY_AT` | `0.8` | Above this share in the middle of a task: the checkpoint is written right away, and the task goes on from it. |
| `RESULT_LIMIT` | `8_000` | A tool result longer than this (in characters) is saved in parts, and the model gets a preview. |
| `RESULT_PART` | `4_000` | The size of each saved part, in characters. Must be at least 500 smaller than `RESULT_LIMIT`. |
| `RESULT_PREVIEW` | `300` | How many characters of a saved result's start, and of its end, are in the preview. |
| `CONTAINER_CMD` | `podman` | The container program. |
| `SANDBOX_MEMORY` / `SANDBOX_CPUS` / `SANDBOX_PIDS` | `2g` / `2` / `512` | Limits for a running sandbox, so a runaway script can't take your computer down. |
| `COMMAND_TIMEOUT` | `600` | Seconds a command in the sandbox (`sandbox_shell`, a notebook call) may run before it is stopped. |
| `SHARED_DIR`, `COMMON`, `ENGINE` | `Shared Folder`, `Common`, `Notebook_Engine` | The folder the sandboxes see parts of, and its two fixed folders. |

All folders and files are defined in `config.py` too. To move or rename one, change it there.

### `Ego/SOUL.md`

Who the assistant is: the start of its system prompt. You write it. If the file is missing or empty, a one-line fallback is used.

## Project layout

```
.
├── main.py                  # start here: the chat loop and the /commands
├── config.py                # every setting and path, read once at the start
├── requirements.txt
├── .env                     # your API key. create it yourself, never commit it
├── classes/
│   ├── agent.py             # the Agent: the model calls, the tool loop, printing, the log, checkpoints
│   └── sandbox.py           # the Sandbox: podman, the container, projects, the network
├── functions/               # small helpers, mostly one job each
│   ├── locks.py             #   "in use" signs between running instances, held by the operating system
│   ├── commands.py          #   what you typed: a message, or which command
│   ├── conversations.py     #   the conversation folders: save, load, list, rename, delete
│   ├── results.py           #   long tool results: save in parts, preview, load
│   ├── load_tools.py        #   find and load every tool in tools/
│   ├── load_skills.py       #   find every skill in skills/
│   ├── read_front_matter.py #   the header of a SKILL.md
│   ├── read_json.py, read_text.py, write_text.py
│   └── environment.py       #   the API key from .env
├── settings/
│   └── model.json           # which model, and how to talk to it
├── Ego/
│   └── SOUL.md              # who the assistant is
├── tools/                   # one file per tool (tools/README.md explains how to write one)
│   ├── basic/               #   calculate, get_time, load_skill, checkpoint
│   ├── results/             #   read_result, search_result
│   ├── sandbox/             #   check_sandbox, open_sandbox, close_sandbox, sandbox_shell, check_projects,
│   │                        #   create_project, mount_project, unmount_project, rename_project, delete_project
│   └── notebook/            #   nb_create, nb_open, nb_close, nb_add, nb_edit, nb_remove, nb_run, nb_show, nb_rerun
├── skills/                  # one folder per skill (skills/README.md explains how to write one)
│   ├── stepwise-calculation/SKILL.md
│   ├── sandbox/SKILL.md     #   how to work in the sandbox and with projects
│   └── notebook/SKILL.md    #   how to work in a notebook
├── Sandboxes/               # one folder per sandbox, a Containerfile inside (Sandboxes/README.md)
│   ├── python/Containerfile #   python 3.12 + numpy, pandas, matplotlib: the one notebooks need
│   └── ubuntu/Containerfile
├── Shared Folder/           # the ONLY folder of your computer a sandbox sees parts of
│   ├── Common/              #   /workspace/Common in every sandbox. created with the first one
│   ├── Notebook_Engine/     #   /workspace/Notebook_Engine, read-only: kernel.py, client.py
│   └── <project>/           #   /workspace/<project>: one at a time per sandbox, made and mounted by the agent
├── Locks/                   # "in use" signs of the running instances. created and cleaned up by itself
└── Conversations/           # your conversations, created with the first one. never on GitHub
    └── <name>/
        ├── state.json       #   what the model carries right now: what /open loads
        ├── log.jsonl        #   every message ever said, one line each. only ever added to
        ├── checkpoint.md    #   the model's notes, once it wrote a checkpoint
        └── results/         #   long tool results: results-1.json, results-2.json, ...
```

## A conversation, drawn

The conversation is one list of messages, and the whole list is sent to the model with every call. Here is one task: you ask something, the model thinks, uses tools, and answers. On the right: which file each part comes from, or goes to.

```
 THE CONVERSATION (what the model gets, every call)                       ON YOUR DISK
 +------------------------------------------------------------------+
 | [0] system   built fresh from parts, always in this order:       |
 |     +--------------------------------------------------------+   |
 |     | 1. who you are, how you work                           |<--+------ Ego/SOUL.md
 |     | 2. your skills: one line each                          |<--+------ skills/*/SKILL.md (only the header)
 |     |    - stepwise-calculation: Use when a calculation ...  |   |
 |     | 3. <checkpoint> your notes </checkpoint>               |<--+------ checkpoint.md (once there is one)
 |     +--------------------------------------------------------+   |
 +------------------------------------------------------------------+
 | [1] user        "A jacket costs 120 €, 20% off, plus 19% tax.    |
 |                  What do I pay? And what does the shop say?"     |
 +------------------------------------------------------------------+
 | [2] assistant   thinking: "a calculation in steps: there is a    |
 |                 skill for that. and I need the shop's page."     |
 |                 tool calls:                                      |
 |                   id call_1  load_skill("stepwise-calculation")  |
 |                   id call_2  fetch_page("shop.example/jacket")   |  (an example tool, see below)
 +------------------------------------------------------------------+
 |                 both run at the same time. their results come    |
 |                 back in the order asked, each with its call's id |
 | [3] tool        id call_1  "---                                  |<---------- skills/stepwise-calculation/SKILL.md
 |                 name: stepwise-calculation ... 1. Write down..." |            (now the whole text)
 | [4] tool        id call_2  "[this result is too long (52,300     |----------> results/results-1.json
 |                 characters). it is saved as results-1, in 14     |            {"1": "...", "2": "...", ...
 |                 parts ... its start and its end:] <html> ..."    |             "14": "..."}
 +------------------------------------------------------------------+
 | [5] assistant   thinking: "step 1: the discount. and find the    |
 |                 price in the page."                              |
 |                 tool calls:                                      |
 |                   id call_3  calculate("120 * 0.8")              |
 |                   id call_4  search_result("results-1", "price") |
 | [6] tool        id call_3  "96.0"                                |
 | [7] tool        id call_4  "part 3, line 212: price 120 € ..."   |<---------- results/results-1.json
 +------------------------------------------------------------------+
 | [8] assistant   tool calls:                                      |
 |                   id call_5  calculate("96 * 1.19")              |
 | [9] tool        id call_5  "114.24"                              |
 +------------------------------------------------------------------+
 | [10] assistant  thinking: "all steps done."                      |
 |                 answer: "1. 20% off: 120 * 0.8 = 96              |
 |                          2. plus 19% tax: 96 * 1.19 = 114.24     |
 |                          You pay 114.24 €. The shop says ..."    |
 +------------------------------------------------------------------+
         |                                          |
         | every message, the moment it arrives     | the whole list without [0], after every message
         v                                          v
   log.jsonl  (one line each, never changed)    state.json  (what /open loads again)
```

And when the conversation gets too full, the model writes its checkpoint, and the list starts over:

```
 BEFORE: [0] system  [1] user  [2] ... [80] assistant         (e.g. 61,000 of 100,000 tokens)
                                    |
                                    |  "[from the program] CHECKPOINT ..."  ->  the model calls checkpoint("## Goal ...")
                                    v
 AFTER:  [0] system   1. who you are   2. skills   3. <checkpoint> ## Goal ... ## Open ... </checkpoint>
                                                         ^
                                                         +---- checkpoint.md
         (everything before is still in log.jsonl and results/)
```

### The same, in words

- **The system prompt comes first, and is built from parts.** First the soul, from `Ego/SOUL.md`: who the assistant is and how it works. Then the skills menu: one line per skill, taken from the header of each `skills/<name>/SKILL.md`. Then, once the model has written one, its checkpoint from `checkpoint.md`. The system prompt is built again from these files whenever needed, never edited by hand.
- **Your question comes next**, as a `user` message.
- **The model answers, maybe with thinking first.** Its thinking is kept in the conversation and the log; whether you see it is set by `PrintThinking`. Instead of answering right away, the model can ask for tools. Each tool call has an id, like `call_1`.
- **Tools run, and their results come back with the same id.** Several calls in one answer run at the same time. Their results go into the list in the order the model asked, and the id tells the model which result belongs to which call.
- **Skills arrive as a tool result.** The system prompt only lists them. When a task matches one, the model calls `load_skill`, and the skill's whole text comes back like any other tool result, here `[3]`. From then on, the model follows it.
- **A long result is pointed to, not given whole.** If a result is longer than `RESULT_LIMIT` characters, like the shop's page in `[4]`, it is saved as `results/results-1.json` in parts, and the model only gets a preview saying where it is. It finds what it needs with `search_result` (`[7]`) and reads a part with `read_result`. `fetch_page` is only an example here: any tool with a long answer is handled like this.
- **The final answer is a message without tool calls.** That ends the task (`[10]`).
- **Everything is logged.** Every message, the moment it arrives, is written as one line into `log.jsonl`, and the system prompt is written too whenever it changed. Nothing in the log is ever changed or removed.
- **The conversation is saved.** After every message, the whole list (without the system prompt, which is built fresh) is written into `state.json`. `/open` loads it again.
- **When it gets too full, it starts over from a checkpoint.** The model writes down where it stands and gives it to the `checkpoint` tool. The list is emptied down to a new system prompt with that checkpoint in it. The log and the results stay, so nothing is lost.

## How it works

### The loop

Everything happens in `Agent.ask` in `classes/agent.py`:

1. Your message is added to the conversation, a list of messages.
2. The whole list is sent to the model. Its answer is printed while it arrives, then added to the list.
3. Did the model ask for tools? Then they run, their results are added, and it goes back to step 2.
4. No tools: that was the final answer, and the task is done.

The model only knows what is in that list. After every message, `main.py` saves it to `state.json`.

### The system prompt

It is built from parts, always in the same order, and is always the first message:

1. the soul (`Ego/SOUL.md`)
2. the skills menu: every skill's name and its one-line description
3. the checkpoint, once there is one

The same parts always give exactly the same text, so the provider's prompt cache stays valid. It is not saved in `state.json`: when a conversation is opened again, it gets a freshly built one, so a changed soul or a new skill is used right away. The log keeps every version of it.

### Tools

A tool is one Python file with two things: `TOOL`, which the model sees (name, description, arguments), and `run`, which the program executes. `functions/load_tools.py` finds every file in `tools/` at the start; there is no list to edit. The model never runs anything itself: it only asks, and the tool's code decides what really happens.

- All tool calls of one answer run at the same time, each in its own thread. The program waits until every one is done, then adds the results in the order the model asked, each with the id of its call.
- A tool never crashes the program. A wrong tool name, broken arguments or an error inside a tool comes back to the model as a text starting with `error:`, so every call always gets an answer.

See [`tools/README.md`](tools/README.md) for how to write one.

### Skills

A skill is a folder in `skills/` with a `SKILL.md` inside: a short header with `name` and `description`, then the instructions. Only the header goes into the system prompt. When a task matches, the model calls `load_skill` and gets the whole text. If there are no skills, the model doesn't get `load_skill` either.

See [`skills/README.md`](skills/README.md) for how to write one.

### Long results

A tool result longer than `RESULT_LIMIT` characters is saved as `results/results-<n>.json`, cut into parts of `RESULT_PART` characters. The model gets a preview: the result's name, its size, how many parts it has, and its start and end. Then:

- `search_result` searches it like `grep`, with grep's options (regex, ignore case, whole word, invert, lines before and after, only matching, count, max count). Every hit says its part and line number.
- `read_result` shows one whole part, never more, so a huge result can't fill the conversation.

If an answer from `search_result` is too long itself, it is saved as a new result, so the model can search that one again, narrower. Everything here is counted in characters, so it works the same with every model.

### Checkpoints

After every answer, the program checks how big the conversation is, using the token count the provider sends with every answer:

- **At the end of a task, above `CHECKPOINT_AT`:** the program asks the model for its checkpoint.
- **In the middle of a task, above `EMERGENCY_AT`:** right after the tool results, the program asks for an emergency checkpoint, in which the model also says where it is in the task.

The model writes its checkpoint in fixed sections (goal, decisions, facts, done, failed, open, files, last exchange) and gives it to the `checkpoint` tool. The tool saves it as `checkpoint.md`, empties the conversation, and builds the system prompt again, with the checkpoint in it. In an emergency, one message tells the model to go on from its checkpoint, and the task continues.

- The log and the saved results are never touched: every word is still there.
- `state.json` becomes empty with the next save, so `/open` starts from the checkpoint too.
- The checkpoint tool refuses when it wasn't asked for.
- A model that ignores the request is asked twice, then left alone for that task, so it is never asked forever.

### The log

`Conversations/<name>/log.jsonl` gets one line for every message: your questions, the model's answers (with their thinking and tool calls), tool results, and the program's own messages to the model. Before a message, the system prompt is written too, but only when it changed. The log is only ever added to, never changed, and never read by the program: whatever happens to the conversation, a message taken back, a checkpoint, a deleted `state.json`, what was said stays in it.

### When things fail

- A busy provider, a timeout or a lost connection is tried again up to 3 times, after 1, 2 and 4 seconds. A wrong key or a bad request is not.
- If a call fails before anything happened, your message is taken back, so you can simply send it again. Work that tools already did stays.
- `state.json` and `checkpoint.md` are written into a temporary file first, then swapped in. A crash in the middle of writing never leaves half a file.

### The sandbox

Everything the model wants run happens in a sandbox: a throwaway Linux container made from one of the `Containerfile`s in `Sandboxes/` (see [`Sandboxes/README.md`](Sandboxes/README.md)). The program never runs anything the model asks for on your computer.

- **One per instance.** Every running `main.py` has at most one container. The agent opens it with `open_sandbox` (picked by reading the Containerfiles with `check_sandbox`) and closes it with `close_sandbox`; leaving the program stops it too. It belongs to the running program, not to a conversation: `/new` and `/open` keep it.
- **Clean every time.** Opening builds the image from the Containerfile (quick when nothing changed) and starts a container with `--rm`. Nothing installed inside survives a stop.
- **What it sees.** `Shared Folder/Common` at `/workspace/Common` (always), `Shared Folder/Notebook_Engine` at `/workspace/Notebook_Engine` (always, read-only), and at most one project at `/workspace/<project>`. All three are mounted `noexec,nosuid,nodev`: nothing in them can be run directly, only through an interpreter inside the container.
- **No network.** The container is disconnected right after it starts, before any command can run (the only thing running is `sleep`), and the program checks it really is: if it can't be sealed, it is stopped again. Only you switch it on, with `/sandbox net on`. A new sandbox the agent opens starts without it again; a restart for a project keeps your choice.
- **Limits.** `no-new-privileges`, memory, CPUs, a process limit, and a time limit for every command (`COMMAND_TIMEOUT`). Longer jobs go into the background, with their output in a file.
- **Labels.** Every container carries who started it (the instance's id), which sandbox, which project, and which copy of this program. That is how an instance finds its own container, and how the containers of a crashed instance are found and removed. Containers you start yourself are never touched.

### Projects

A project is a folder directly in `Shared Folder`, except `Common` and `Notebook_Engine`. The agent can `create_project`, `mount_project`, `unmount_project`, `rename_project` and `delete_project`, and `check_projects` shows each one as free, mounted here, or mounted by another instance.

- One project per sandbox at a time. Podman can't add a folder to a running container, so mounting or unmounting restarts the sandbox. That's why `open_sandbox` takes a project too.
- A project mounted by one instance can't be mounted, renamed or deleted by another. This is a lock (`project-<name>`) the mounting instance holds: taking it is one step, so two instances asking at the same moment can never both get it, and the operating system frees it if the instance crashes. Rename and delete hold that lock while they work, so nobody can mount the folder halfway.
- `Common` and `Notebook_Engine` are refused by every project tool, in any spelling. Links to folders elsewhere are not projects, because a sandbox could reach outside `Shared Folder` through them.

### Notebooks

The `nb_*` tools give the model Jupyter notebooks that run inside the sandbox. The engine is `Shared Folder/Notebook_Engine` (taken over from the original AI-Harness), which the sandbox sees read-only:

- `kernel.py` is the kernel of one open notebook. It keeps running in the sandbox, holds the variables and the cells, and writes the whole `.ipynb` after every change.
- `client.py` runs once per tool call. It starts a kernel (`nb_create`, `nb_open`), stops one (`nb_close`), or hands the command to the running one. The command arrives base64-encoded, so code with quotes or `$` can't confuse the shell.
- `tools/notebook/_notebook.py` is the side on your computer: it checks the path (it must be inside `Common/` or the mounted project and end in `.ipynb`; `common/x.ipynb` is fine too), locks the notebook so no other instance can open it at the same time, and sends the command through `sandbox_shell`'s way in.

Every answer ends with an overview of all cells (id, state, first line), so the model always sees where it is. The `notebook` skill tells it how to work: a plan cell at the top, one step per cell, fix cells in place, `nb_rerun` at the end. Notebooks need `python3` in the sandbox, e.g. `python`. A restart of the sandbox (mounting, unmounting, closing) stops every kernel; the files stay.

### Several instances at once

Every `main.py` is an instance with its own id (process number + start time). Each holds a lock `instance-<id>` as long as it runs; that's how the others know it is alive. A lock is a file in `Locks/` that the instance keeps open with a lock from the operating system on it, so the operating system frees it when the instance ends, however it ends. At every start, the lock files nobody holds and the containers of instances that are gone are cleaned up.

| Lock | Held | Keeps out |
|---|---|---|
| `instance-<id>` | while the instance runs | nothing: it says "alive" |
| `project-<name>` | while this instance's sandbox has it mounted, and for the moment of a rename or delete | other instances mounting, renaming or deleting it |
| `notebook-<hash>` | from `nb_create`/`nb_open` until `nb_close`, or until the sandbox stops | another instance's kernel saving over this one's work |

Conversations themselves are not locked: don't `/open` the same conversation in two instances at once.

### How the model keeps track

The model doesn't have to remember what runs: the program tells it, in three places.

1. **The system prompt** ends with the workspace as it was when the context started: which sandbox runs, the project, the network, the open notebooks, the sandboxes and projects there are. It is built whenever the context starts fresh (a new conversation, `/open`, after a checkpoint), so right after a checkpoint empties the conversation, the model still knows exactly what runs.
2. **Tool results** are newer than that: every tool that changes something ends its answer with one line of the state now, e.g. `[now: sandbox python runs, project website, working folder /workspace/website, network off, open notebooks: website/sales.ipynb]`. Notebook answers end with the overview of all cells. `check_sandbox` and `check_projects` show everything at any time.
3. **Your changes** with `/sandbox net` or `/sandbox close` are told to the model with your next message.

What the program can't know is *why* a file exists. That goes into the model's own notes: the checkpoint's `## Files` section asks for the files, notebooks and projects that matter, each with what it is for, and the `notebook` skill keeps a plan cell at the top of every notebook. Everything else (long outputs, every message) is in `results/` and `log.jsonl` as before.

## Extending it

- **A sandbox:** a new folder in `Sandboxes/` with a `Containerfile`. See [`Sandboxes/README.md`](Sandboxes/README.md). No restart needed.
- **A tool:** a new `.py` file in `tools/`, with `TOOL` and `run`. See [`tools/README.md`](tools/README.md).
- **A skill:** a new folder in `skills/` with a `SKILL.md`. See [`skills/README.md`](skills/README.md).
- **A command:** one line in `COMMANDS` in `functions/commands.py`, and its part in `main.py`.

Tools and skills are read once, when the program starts: restart it after adding or changing one.
