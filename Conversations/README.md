# Conversations

Your conversations: one folder each, named after the conversation. The program creates a folder with the first message in it, and saves into it after every message. Only this README is on GitHub: the conversations themselves are private, so `.gitignore` keeps them off.

```
Conversations/
└── 20261024-01-10-05/          the name: when it was started (year month day - hour - minute - second)
    ├── state.json              what the model carries right now: what /open loads
    ├── log.jsonl               every message ever said, one line each
    ├── checkpoint.md           the model's notes on where it stands (once it wrote one)
    └── results/                long tool results (once there was one)
        ├── results-1.json
        └── results-2.json
```

The code for all of this is in `functions/conversations.py` (the folders and `state.json`), `functions/results.py` (`results/`), `classes/agent.py` (the log) and `tools/basic/checkpoint.py` (`checkpoint.md`).

## The files

### state.json

The conversation as it is right now, replaced after every message:

```json
{
 "messages": [
  {"role": "user", "content": "what is 17% of 2340?"},
  {"role": "assistant", "reasoning_content": "...", "tool_calls": [ ... ]},
  {"role": "tool", "tool_call_id": "call_1", "name": "calculate", "content": "397.8"},
  {"role": "assistant", "content": "17% of 2340 is 397.8"}
 ],
 "tokens": 1830
}
```

- `messages`: every message since the start, or since the last checkpoint. The system prompt is **not** in it: it is built fresh when the conversation is opened, from the soul, the skills and the checkpoint as they are then.
- `tokens`: how big the conversation was after its last answer.
- After a checkpoint, `messages` is empty: everything is in `checkpoint.md` then.

### log.jsonl

Every message ever said in this conversation, one JSON object per line: your questions, the model's answers (with their thinking and tool calls), tool results, and the program's own messages to the model. Before a message, the system prompt, but only when it changed:

```
{"time": "2026-10-24T01:10:07", "kind": "system", "content": "# Who you are ..."}
{"time": "2026-10-24T01:10:07", "kind": "message", "message": {"role": "user", "content": "what is 17% of 2340?"}}
{"time": "2026-10-24T01:10:09", "kind": "message", "message": {"role": "assistant", "tool_calls": [ ... ]}}
```

It is only ever added to: nothing in it is changed or removed, also not by a checkpoint, `/open` or a failed message. And the program never reads it: it is for you, to see exactly what happened and what the model was sent. Search it with `grep`, or read any line with a JSON reader.

### checkpoint.md

The model's own notes, in fixed sections: goal, decisions, facts, done, failed, open, files, last exchange. Written by the `checkpoint` tool when the conversation got too full, replacing the one before (every version is still in the log). It goes into the system prompt, so the model has it in every call from then on, also after `/open`.

### results/

Tool results too long for the conversation (longer than `RESULT_LIMIT` characters in `config.py`). Each one is cut into parts:

```json
{"1": "the first 4000 characters ...", "2": "the next 4000 ...", "3": "..."}
```

The conversation only has a preview of it, with its name (`results-1`). The model reads a part with `read_result` and searches it with `search_result`, and only ever the results of its own conversation. The numbers go on across checkpoints and `/open`, so a name is never used twice in one conversation.

## The commands

| Command | What it does to the folders |
|---|---|
| `/new` | A new name. Its folder appears with the first message. |
| `/list` | Lists the folders that have a `state.json` or a `log.jsonl`. |
| `/open <name>` | Loads its `state.json`. The system prompt is built fresh, with its `checkpoint.md` if there is one. |
| `/rename <old> <new>` | Renames the folder, with everything in it. Names: letters, digits and `- _ .`, at most 60 characters. |
| `/delete <name>` | Deletes the folder with everything in it, after you type `yes`. There is no undo. |

## Changing things by hand

The program is fine with it, as long as that conversation isn't open in it right now (then it saves over your change with the next message):

- **Delete `state.json`:** `/open` starts with no messages, but with the checkpoint, if there is one.
- **Delete `checkpoint.md`:** the next time the conversation is opened, its system prompt has no checkpoint.
- **Delete `log.jsonl`:** nothing breaks. The log simply starts again with the next message.
- **Delete a file in `results/`:** the model gets "there is no result called ..." when it asks for it.
- **Edit `state.json`:** fine, if it stays valid JSON. A broken file ends the program when you `/open` it, with an error saying where in the file it is broken. Fix the file (or delete it), then start again.
