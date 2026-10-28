# tools

Everything the agent can *do* is a tool, and every tool is one Python file in here. The model never runs anything itself: it only **asks** for a tool by name, and the code in the tool's file decides what really happens.

| Tool | File | What it does |
|---|---|---|
| `calculate` | `basic/calculate.py` | Evaluates a math expression, e.g. `0.17 * 2340`. Only digits and math symbols, in its own process, stopped after 5 seconds. |
| `get_time` | `basic/get_time.py` | The current date, time (with milliseconds) and weekday: the user's own, or of any time zone by its IANA name (`Europe/Berlin`). The model has no clock, so it asks this whenever "today" matters. |
| `load_skill` | `basic/load_skill.py` | Returns the full instructions of a skill (`skills/<name>/SKILL.md`) by its name. Taken away from the model when there are no skills. |
| `checkpoint` | `basic/checkpoint.py` | Saves the model's checkpoint as `checkpoint.md`, empties the conversation and puts the checkpoint into the system prompt. Only works when the program asked for it: when the conversation got too full (`CHECKPOINT_AT`, `EMERGENCY_AT` in `config.py`). The log and the saved results stay. |
| `read_result` | `results/read_result.py` | Shows **one** part of a saved result (see "Long results" below). Never more than one, so a huge result can't fill the context. |
| `search_result` | `results/search_result.py` | `grep` for one saved result: every matching line with its part and line number. With grep's options: regex, ignore case, whole word, invert, lines before/after, only the matched piece, count, max count. |
| `check_sandbox` | `sandbox/check_sandbox.py` | Every sandbox with its whole Containerfile and its settings (`sandbox.json`), and which one runs here. Changes nothing. |
| `open_sandbox` | `sandbox/open_sandbox.py` | Builds and starts a sandbox for this instance, network off, optionally with projects mounted right away. |
| `close_sandbox` | `sandbox/close_sandbox.py` | Stops it. Its projects are free for other instances again. |
| `sandbox_shell` | `sandbox/sandbox_shell.py` | Runs a bash command inside, and returns what it printed. Stopped after `COMMAND_TIMEOUT` seconds. |
| `check_projects` | `sandbox/check_projects.py` | The project folders: free, mounted here, or mounted by another running instance. |
| `create_project` | `sandbox/create_project.py` | A new, empty folder `Shared Folder/<name>`. |
| `mount_project` | `sandbox/mount_project.py` | Mounts one more project at `/workspace/<name>`; the others stay. Restarts the sandbox. |
| `unmount_project` | `sandbox/unmount_project.py` | Unmounts one project; the others stay. Restarts the sandbox. |
| `rename_project` | `sandbox/rename_project.py` | Renames a project folder nobody has mounted. Never a read-only one. |
| `delete_project` | `sandbox/delete_project.py` | Deletes a project folder with everything in it, if nobody has it mounted. Never a read-only one. |
| `nb_create` | `notebook/nb_create.py` | Makes a new notebook in `Common/` or a mounted project and starts its kernel. |
| `nb_open` | `notebook/nb_open.py` | Opens an existing notebook (starting its kernel) and returns all of it. Already open? Its variables are kept. |
| `nb_close` | `notebook/nb_close.py` | Stops a notebook's kernel. Its variables are gone, the file stays. |
| `nb_add` | `notebook/nb_add.py` | Adds a code or markdown cell, at the end or after a given cell, optionally running it. |
| `nb_edit` | `notebook/nb_edit.py` | Replaces a cell's whole code, optionally running it. |
| `nb_remove` | `notebook/nb_remove.py` | Removes a cell. |
| `nb_run` | `notebook/nb_run.py` | Runs one or more cells, in the order given. |
| `nb_show` | `notebook/nb_show.py` | Returns the whole notebook: every cell with code and output. |
| `nb_rerun` | `notebook/nb_rerun.py` | Fresh kernel, then every cell from the top. |

The sandbox and notebook tools are thin: the work is in `classes/sandbox.py` (and `notebook/_notebook.py`), which they reach as `agent.sandbox`. Without Podman, `main.py` takes the whole `sandbox/` and `notebook/` folders away from the model.

## How a tool file looks

Every tool file has exactly two things: `TOOL` and `run`.

```python
# tools/word_count.py

def run(agent, text):
    return str(len(text.split()))

TOOL = {
    "name": "word_count",
    "description": "Count the words in a text. Use it whenever the user asks how long a text is.",
    "parameters": {"type": "object",
                   "properties": {"text": {"type": "string", "description": "the text to count"}},
                   "required": ["text"]},
}
```

### `TOOL`: what the model sees

| Key | What it is |
|---|---|
| `name` | The name the model uses to ask for the tool. Lowercase, with `_` between words. Must be unique. |
| `description` | When and how to use the tool. **This is an instruction to the model**, not documentation for you: it decides whether the model ever calls the tool. Say *when* to use it, not only *what* it does. |
| `parameters` | The arguments, as a JSON schema: a `type: object` with `properties` (one entry per argument, each with a `type` and a `description`) and `required` (the arguments that must always be there). |

Argument types you will use most: `"string"`, `"integer"`, `"number"`, `"boolean"`, `"array"` (with `"items": {"type": ...}`). An optional argument is one that is not in `required`; give it a default value in `run`.

A tool without arguments:

```python
"parameters": {"type": "object", "properties": {}}
```

### `run`: what happens

- It **always gets the calling agent first**, then the arguments the model passed, **by name**. The model's `{"text": "hello world"}` becomes `run(agent, text="hello world")`. Don't need the agent? Just ignore it.
- The argument names in `run` must be exactly the names in `properties`.
- Optional arguments need a default: `def run(agent, text, ignore_numbers=False):`
- Whatever `run` returns goes back to the model **as text**. A number is turned into text for you (`str(...)`), but return text yourself, so you decide what it looks like.

## How to make a new tool

1. Create a new file in this folder, e.g. `tools/word_count.py`.
2. Write `run` and `TOOL`, like the example above.
3. Start `python main.py` again. The start line lists every tool it found:
   ```
   model: deepseek/deepseek-flash | tools: calculate, word_count   (/exit to leave)
   ```

That's all. There is no list to add it to and no import to write: `functions/load_tools.py` finds every file by itself when the program starts.

## The rules the loader follows

- **Every `.py` file in here is a tool**, also in subfolders, as deep as you like (`tools/text/word_count.py`). The folders are only for you to keep order: the model only ever sees the `name` in `TOOL`.
- **Files and folders starting with `_` are skipped**: `_helpers.py`, `_drafts/`. That's where shared helper code goes. A tool uses a helper next to it with `from . import _helpers`.
- **Anything that isn't a `.py` file is ignored**, like this README.
- **Two tools with the same `name` stop the program** at start, naming both files:
  `two tools are called 'calculate': tools/basic/calculate.py and tools/math/calc2.py. rename one`
- **A `.py` file without `TOOL` or `run` stops the program** too, so a half-written tool is noticed right away.

## What happens when the model calls a tool

1. The model answers with one or more tool calls. Each has an **id** (e.g. `call_aaa`), the tool's name, and its arguments as JSON text.
2. All tool calls of one answer **run at the same time**, each in its own thread (`run_tools` in `classes/agent.py`).
3. When **every** one is done, the results go into the conversation **in the order the model asked**, each with the id of its call. That id is how the model knows which result belongs to which call.
4. The model is asked again, now with the results. It may ask for more tools, or give its final answer.

## Errors

An error never crashes the program, and every call always gets an answer. Whatever goes wrong comes back to the model as a text starting with `error:`, so it can try again:

| What went wrong | What the model gets |
|---|---|
| it asked for a tool that doesn't exist | `error: Exception: there is no tool called 'x'. yours: calculate` |
| its arguments are broken JSON | `error: JSONDecodeError: ...` |
| a wrong or missing argument name | `error: TypeError: run() got an unexpected keyword argument 'expr'` |
| your `run` raised an exception | `error: ZeroDivisionError: division by zero` |

So inside `run` you don't need `try` for everything. But when you *expect* a problem, return a clear text yourself: it helps the model more than a raw error. Say what was wrong and what to do instead, e.g. `"invalid expression: only digits, spaces and + - * / ( ) . % are allowed"`.

## Long results

A tool result longer than `RESULT_LIMIT` characters (8,000, in `config.py`) is not given to the model whole. `functions/results.py` cuts it into parts of `RESULT_PART` characters (4,000) and saves it in the conversation's folder:

```
Conversations/<name>/results/results-1.json     {"1": "the first 4000 characters", "2": "the next 4000", ...}
Conversations/<name>/results/results-2.json     the next long result
```

The model gets a preview instead: the result's name, its size, how many parts it has, and its first and last `RESULT_PREVIEW` characters (300). Then:

- **`search_result`** glues the parts back together and searches them like `grep`, with their part and line number. It has grep's options as named settings: `regex` (-E), `ignore_case` (-i), `whole_word` (-w), `invert` (-v), `before` / `after` (-B / -A), `only_matching` (-o), `count` (-c), `max_count` (-m). It is written with Python's `re`, not the grep program, so it works the same on every system; regular expressions use Python's syntax, which is nearly the same as `grep -P`.
- **`read_result`** shows one whole part. For more, the model asks for the next part.

An answer from `search_result` that is too long is saved as a new result too. That is on purpose: the model can search that one again, narrower. Everything is counted in characters, not tokens, so it works the same with every model. The model can only reach its own conversation's results.

## Good to know

- **Never trust the arguments.** They come from the model, and the model can be wrong or tricked by text it read. Check them before you use them: allowed characters, allowed folders, sizes. Never pass them to `eval`, a shell, or a file path without checking. `calculate.py` shows how.
- **Tools run in parallel.** Two calls of the same tool can run at the same time. If a tool changes something shared (a file, a variable), make sure two runs at once can't get in each other's way.
- **Keep results short.** Every result is sent to the model again with every later call. A tool that returns a whole file fills the conversation fast: return what matters, or a summary.
- **Things that can hang get a time limit**, like the 5 seconds in `calculate.py`. Otherwise the agent waits forever.
- **Every agent gets every tool** in this folder, for now. (Exception: without Podman, the `sandbox/` and `notebook/` folders are left out.)
- **Run nothing on the user's computer.** A tool that needs to run code passes it to `agent.sandbox.exec(...)`, like `sandbox_shell` does.
