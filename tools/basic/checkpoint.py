# tools/basic/checkpoint.py — the model saves its checkpoint, and the conversation starts fresh from it.
# the program asks for it (classes/agent.py, ask): when a task ended above CHECKPOINT_AT of the context limit, or in
# the middle of a task above EMERGENCY_AT. the model writes the checkpoint and gives it to this tool, which:
#   1. saves it as checkpoint.md in the conversation's folder (replacing the old one)
#   2. empties the conversation: everything said so far is in the checkpoint now
#   3. builds the system prompt again: it has the checkpoint in it from now on (see build_system)
# the log and the saved results are NOT touched: every word is still in log.jsonl, every long result in results/.
# state.json becomes empty with the next save (functions/conversations.py), so /open starts from the checkpoint too.

import litellm
from functions.write_text import write_text


def run(agent, text):
    if not agent.checkpoint_asked:                   # only when the program asked: called at any other time, it
        return ("not now: write a checkpoint only when the program asks you for one, "   # would throw away the
                "because it empties your whole conversation")                            # conversation for nothing
    if not text.strip():
        return "the checkpoint is empty: write it, with every section, then call checkpoint again"
    if not agent.checkpoint_file:                    # an agent without a conversation folder
        return "there is no place to save a checkpoint for you. go on without one"

    write_text(agent.checkpoint_file, text)          # 1. checkpoint.md: replaces the old one. the folder is made if
                                                     #    it doesn't exist yet
    agent.conversation.clear()                       # 2. the conversation is empty: it is all in the checkpoint now
    agent.refresh_system()                           # 3. the new system prompt, with the checkpoint in it
    agent.tokens = litellm.token_counter(model=agent.model, messages=agent.conversation)   # its new size. an
                                                     # estimate: there is no answer from the provider yet to count it
    agent.cleared = True                             # tells run_tools and ask: the conversation was just emptied
    return "checkpoint saved, the conversation starts fresh from it (" + str(len(text)) + " characters)"


TOOL = {
    "name": "checkpoint",
    "description": "Save your checkpoint: your notes on where you stand. It replaces your whole conversation: "
                   "afterwards you only have your system prompt, with this checkpoint in it. Only call it when the "
                   "program asks you for a checkpoint, and then call nothing else in the same reply.",
    "parameters": {"type": "object",
                   "properties": {"text": {"type": "string", "description": "the whole checkpoint, in markdown, with "
                                                                            "the sections the program asked for"}},
                   "required": ["text"]},
}
