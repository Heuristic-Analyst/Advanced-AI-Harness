# functions

Small helpers the rest of the program uses: reading and writing files, finding tools and skills, the conversation folders, long results, the commands. Most files do one job.

None of them talks to the model: that is `classes/agent.py`. And none of them is a tool: tools live in `tools/`, and the model can only reach what a tool gives it.

## The files

| File | Functions | What for | Used by |
|---|---|---|---|
| `read_json.py` | `read_json(file_path)` | A JSON file as Python data. Missing or broken: an error naming the file. | `config.py`, `conversations.py`, `results.py` |
| `read_text.py` | `read_text(file_path)` | A whole text file, without spaces around it. Missing: an empty text, no error. | `main.py` (the soul), `agent.py` (the checkpoint), `load_skill` |
| `write_text.py` | `write_text(file_path, text)` | Writes a text file, creating its folder if needed. Crash-safe: a temporary file first, then swapped in. | the `checkpoint` tool |
| `environment.py` | `read_key(provider, file_path)` | The line `PROVIDER_API_KEY=...` from `.env`. None if there is none. The key never goes into the environment. | `config.py` |
| `read_front_matter.py` | `read_front_matter(file_path)` | Splits a file into its header (between two `---` lines, `key: value` each) and its body. | `load_skills.py` |
| `load_tools.py` | `load_tools(folder)` | Finds and loads every tool in `tools/`, also in subfolders. Stops the program on two tools with one name, or a file without `TOOL` and `run`. | `main.py` |
| `load_skills.py` | `load_skills(folder)` | Finds every `skills/<name>/SKILL.md` and keeps its name and description. Stops the program on two skills with one name, or a skill without a description. | `main.py` |
| `commands.py` | `COMMANDS`, `help_text()`, `usage(command)`, `check_input(text)` | Decides what you typed: a message for the model, or which command, with the right number of words. Prints the help and "command not found" itself. | `main.py` |
| `conversations.py` | `new_name()`, `names()`, `exists()`, `name_problem()`, `save()`, `load()`, `rename()`, `delete()`, and `folder_of`, `state_of`, `log_of`, `results_of`, `checkpoint_of` | Everything about `Conversations/`: the paths of each file, saving and loading `state.json`, and the folders behind `/new`, `/list`, `/open`, `/rename`, `/delete`. | `main.py` |
| `results.py` | `shorten(folder, text)`, `save()`, `next_number()`, `preview()`, `load(folder, name)`, `not_found()` | Long tool results: saved in parts as `results-<n>.json`, a preview for the model, and loading them back. | `agent.py` (`shorten`), the `read_result` and `search_result` tools |

## How they are used

They are imported like any Python file in a folder:

```python
from functions.read_text import read_text      # one function
from functions import conversations            # a whole file: conversations.save(...), conversations.load(...)
```

That works because `main.py` is started from the project's folder: Python then finds `functions/` next to it. A file here may use another one the same way (`results.py` uses `read_json.py`).

## Good to know

- **Errors that matter stop the program, the rest don't.** A missing `model.json` or two tools with one name stop it at the start, with a message saying what to fix. A missing soul just means an empty text, because the caller has a fallback.
- **Names from the model are checked here, never trusted.** `conversations.py` only accepts names made of letters, digits and `- _ .`, and `results.py` only names like `results-3`. So nothing can point outside its folder, like `../../.env`.
- **Writing is crash-safe.** `save()` in `conversations.py` and `write_text()` first write into a `.saving` file, then swap it in with `os.replace`, in one step. A crash while writing never leaves half a file.
- **Adding one:** a new `.py` file here, with a docstring saying what it does. Import it where it is needed.