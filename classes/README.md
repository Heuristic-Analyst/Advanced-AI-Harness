# classes

| File | What it is |
|---|---|
| `agent.py` | The `Agent`: one conversation with one model. It sends the conversation to the model, prints the answer, runs the tools, logs every message, and asks for checkpoints. |
| `sandbox.py` | The `Sandbox`: this instance's container (Podman), its projects, its settings (`Sandboxes/<name>/sandbox.json`), the network. Everything that talks to Podman. |
| `terminal.py` | The `Terminal`: one bash that stays open inside the container (`podman exec -i`), for the `terminal` tool. Commands go in, the output comes back up to a marker line; too slow = ctrl+c for that command only. |
| `relay.py` | The `Relay`: the door from your computer (127.0.0.1) into a sandbox's "view" port, through `podman exec`. |

`main.py` makes one `Agent` per conversation (`new_agent`), and calls `agent.ask(text)` for every message you type. Everything the agent needs comes in as a parameter, so `agent.py` itself knows nothing about folders or files: `main.py` tells it.

## Making an agent

```python
agent = Agent(MODEL, API_KEY, instructions=soul, stream=STREAM, effort=EFFORT, print_thinking=PRINT_THINKING,
              tools=tools, skills=skills, conversation=messages,
              log_file=..., results_dir=..., checkpoint_file=..., context_limit=CONTEXT_LIMIT)
```

| Parameter | What it is | Left out |
|---|---|---|
| `model`, `api_key` | which model, and the key for it (from `config.py`) | required |
| `instructions` | who the agent is: the soul, the start of its system prompt | no soul |
| `stream` | print the answer piece by piece while it arrives | all at once |
| `effort` | how hard the model thinks | the model's default |
| `print_thinking` | also print the thinking | only the answer |
| `tools` | the tools it may use: name -> `{"schema", "run"}` (`functions/load_tools.py`) | no tools |
| `skills` | the skills it may load: name -> `{"description", "path"}` (`functions/load_skills.py`) | no skills |
| `conversation` | a saved list of messages to go on with (`/open`) | a new conversation |
| `log_file` | where every message is written (`log.jsonl`) | no log |
| `results_dir` | where long tool results are saved (`results/`) | long results are given whole |
| `checkpoint_file` | where the checkpoint is (`checkpoint.md`) | no checkpoints |
| `context_limit` | tokens the conversation may have | no checkpoints are asked for |

Pass them by name (`stream=STREAM`), never by position: then a value can never land in the wrong parameter.

## What it holds

| Variable | What it holds |
|---|---|
| `conversation` | the list of messages: the only thing the model ever knows. The system prompt is always at position 0 |
| `tokens` | how big the conversation is, as the provider counted it with the last answer |
| `printing` | what was printed last: `"THINKING"`, `"ANSWER"` or `None`, so a title is printed when it changes |
| `logged_system` | the system prompt as it was last written into the log, so it is only logged again when it changes |
| `checkpoint_asked` | `None`, or why a checkpoint was asked for: `"end"` or `"emergency"` |
| `cleared` | `True` right after the `checkpoint` tool emptied the conversation |

The parameters above are kept under the same names (`agent.model`, `agent.tools`, ...). Tools get the agent as their first argument, so they can use all of this: `load_skill` reads `agent.skills`, `read_result` uses `agent.results_dir`, `checkpoint` empties `agent.conversation`.

## What it does

| Function | What it does |
|---|---|
| `ask(text)` | **The loop.** Adds your message, then: call the model, add its answer, run the tools it asked for, again, until it answers without tools. Checks the size after every answer and asks for a checkpoint when needed. Returns the final answer as text. |
| `call_model()` | One call to the model, with the whole conversation and the tools. A busy provider, a timeout or a lost connection is tried again after 1, 2 and 4 seconds. |
| `show(response)` | Prints the thinking and the answer while they arrive (streaming) or at once, and returns the finished response. |
| `print_part(kind, text)` | Prints one piece of `THINKING` or `ANSWER` text, with a title when the kind changes. Hidden thinking is skipped. |
| `count_tokens(response)` | The conversation's size, from the provider's count in the answer. No count: litellm's estimate. |
| `run_tools(tool_calls)` | Runs all tool calls of one answer at the same time, waits for all of them, and adds their results in the order the model asked, each with its call's id. Long results are shortened first (`functions/results.py`). |
| `run_tool(call, results)` | Runs one tool call, in its own thread. Never fails: every problem becomes an `error:` text for the model. |
| `build_system()` | Puts the system prompt together: the soul, the skills menu, the checkpoint. Changes nothing. |
| `refresh_system()` | Builds the system prompt and puts it at position 0: replaces the old one, or adds it. No text: no system message. |
| `log(message)` | Writes one message into the log, with the system prompt before it if it changed. Only ever adds. |
| `too_full(share)` | Is the conversation above this share of the context limit? |
| `ask_for_checkpoint(why)` | Adds the request for a checkpoint (`"end"` or `"emergency"`) as the next message to the model. |
| `tell_model(text)` | Adds a message from the program (not from you) to the conversation and the log. |

## One message, from start to end

```
ask("what is 17% of 2340?")
 |
 |  add your message to the conversation, and log it
 v
 +-> call_model()  ->  show()  ->  add the answer, log it, count the tokens
 |        |
 |        +-- tools asked for?  yes: run_tools() -> results added (in order, with their ids)
 |        |                          - the checkpoint tool emptied the conversation?
 |        |                              end of a task: done.   in a task: "go on", back to the top
 |        |                          - above EMERGENCY_AT: add the emergency request
 |        |                          back to the top
 |        |
 |        +-- no tools: the final answer
 |                 - above CHECKPOINT_AT: add the request, back to the top
 +---------------- - otherwise: return the answer
```

If the model call fails before anything happened, your message is taken back, so the conversation is as before and you can send it again. If tools already ran, their work stays.

## The texts at the top of the file

- `CHECKPOINT_REQUEST`, `EMERGENCY_NOTE`, `GO_ON` are what the program says to the model about checkpoints. They start with `[from the program, not the user]`, so the model doesn't think you wrote them. Change the wording there.
- `RETRIES` and `RETRY_ON` say how often, and for which errors, a model call is tried again.