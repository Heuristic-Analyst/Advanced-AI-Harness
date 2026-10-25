# Basic AI Harness, from scratch

A small AI assistant that runs in your terminal, built step by step so that every line is understood. It talks to any model through [LiteLLM](https://github.com/BerriAI/litellm), can use tools, loads skills when it needs them, saves every conversation, and keeps working when a conversation gets too long for the model.

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

## How it fits together

- **`main.py`**: the chat loop. It reads what you type, sends `/commands` to `functions/commands.py`, and gives every other message to `agent.ask(text)`. After every message, also a failed one, it saves the conversation to `state.json`.
- **`classes/agent.py`**: the heart of the program. `ask()` is the loop: call the model, add its answer to the conversation, run the tools it asked for, and go again until it answers without tools. `call_model()` tries again on errors that may go away by themselves (3 times, after 1, 2 and 4 seconds). `show()` prints the answer while it streams in, then glues the pieces back into one finished answer.
- **The system prompt**: built fresh from three parts, always in this order: `Ego/SOUL.md`, the skills menu, `checkpoint.md`. It is never saved in `state.json`. The same order always gives the same text, so the provider's prompt cache stays valid.
- **Tools**: one file each in `tools/`, with `TOOL` (what the model sees) and `run(agent, **args)` (what the program does). They are found at the start, with no list to edit. All tool calls of one answer run at the same time, each in its own thread. Their results go back in the order the model asked, each with its call's id. Any problem comes back as a text starting with `error:`, so every call always gets an answer.
- **Skills**: only the name and description of each `SKILL.md` are in the system prompt. When a task matches, the model calls `load_skill` and gets the whole text back as a tool result. No skills: no `load_skill` either.
- **Long results**: a tool result longer than 8,000 characters is saved in 4,000-character parts as `results/results-<n>.json`. The model gets a preview with the start, the end and the number of parts. It reads one part with `read_result`, or finds lines with `search_result`, a grep with grep's options (`-E -i -w -v -A -B -o -c -m`). If a search answer is too long itself, it is saved as a new result.
- **Checkpoints**: the conversation's size comes from the token count the provider sends with every answer. A task that ended above 60% of `ContextLimit` gets a checkpoint request. Above 80% in the middle of a task, an emergency request comes right after the tool results. The model writes its notes in fixed sections (Goal, Decisions, Facts, Done, Failed, Open, Files, Last exchange) and gives them to the `checkpoint` tool. The tool saves `checkpoint.md`, empties the conversation, and builds the system prompt again with the checkpoint in it. The tool refuses when nobody asked, and the program asks at most twice per task.
- **Saving**: every conversation is a folder. `state.json` is what the model carries right now, written to a temporary file first and then swapped in. `log.jsonl` gets every message ever said, and the system prompt whenever it changed. It is only ever added to, and the program never reads it.
- **Safety**:
  - `calculate` only accepts digits and math symbols, and runs in its own isolated Python process (`-I`) that is stopped after 5 seconds.
  - Conversation, result and time zone names are checked against a pattern, so the model can never point the program at another folder or file.
  - The API key is read from `.env`, but never put into the environment.

## Requirements

- Python 3.10 or newer
- An API key for your model provider (not needed for local models such as Ollama)

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
model: deepseek/deepseek-flash | tools: calculate, checkpoint, get_time, load_skill, read_result, search_result | skills: stepwise-calculation
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
| `/help` | Show the command list. |
| `/exit`, `/quit` | Leave. Ctrl+C or Ctrl+D leave too. Everything is saved already. |

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
│   └── agent.py             # the Agent: the model calls, the tool loop, printing, the log, checkpoints
├── functions/               # small helpers, mostly one job each
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
│   └── results/             #   read_result, search_result
├── skills/                  # one folder per skill (skills/README.md explains how to write one)
│   └── stepwise-calculation/SKILL.md
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

## Extending it

- **A tool:** a new `.py` file in `tools/`, with `TOOL` and `run`. See [`tools/README.md`](tools/README.md).
- **A skill:** a new folder in `skills/` with a `SKILL.md`. See [`skills/README.md`](skills/README.md).
- **A command:** one line in `COMMANDS` in `functions/commands.py`, and its part in `main.py`.

Tools and skills are read once, when the program starts: restart it after adding or changing one.
