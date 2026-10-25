# settings

How the program talks to the model. Everything here is read once, when the program starts: change something, then start `python main.py` again.

| File | What it is |
|---|---|
| `model.json` | Which model, and how to use it. |

## model.json

```json
{
  "Model": "deepseek/deepseek-flash",
  "Stream": true,
  "Effort": "high",
  "PrintThinking": true,
  "ContextLimit": 100000
}
```

| Setting | Required | Default | What it does |
|---|---|---|---|
| `Model` | yes | | The model, as LiteLLM names it: `provider/model`. |
| `Stream` | no | `false` | `true`: the answer is printed piece by piece while it arrives. `false`: all at once, when it is complete. |
| `Effort` | no | the model's own | How hard the model thinks before it answers: `low`, `medium` or `high` (DeepSeek: `low`, `high`, `max`). A model that can't think simply ignores it. |
| `PrintThinking` | no | `false` | `true`: the model's thinking is printed too, under `THINKING:`. `false`: only the answer. Either way it is kept in the conversation and the log. |
| `ContextLimit` | no | `100000` | Tokens a conversation may have at most. Checkpoints are written at 60% and 80% of it (`CHECKPOINT_AT`, `EMERGENCY_AT` in `config.py`). **Set it to your model's real context window, or a bit below**: too high, and the model's real limit is hit before any checkpoint. |

`config.py` reads this file into `MODEL`, `STREAM`, `EFFORT`, `PRINT_THINKING` and `CONTEXT_LIMIT`. A missing `model.json` stops the program at the start with an error naming the file, and so does a file that isn't valid JSON (the error says where in the file).

## Changing the model

Only `Model` has to change, plus the key in `.env` if it's a new provider:

| Provider | `Model` | Line in `.env` |
|---|---|---|
| DeepSeek | `deepseek/deepseek-flash` | `DEEPSEEK_API_KEY=sk-...` |
| Anthropic | `anthropic/<model>` | `ANTHROPIC_API_KEY=sk-ant-...` |
| OpenAI | `openai/<model>` | `OPENAI_API_KEY=sk-...` |
| Ollama (local) | `ollama/llama3` | none needed |

The key's name is always the part before the `/` in capitals, plus `_API_KEY`. The key itself never goes in here: it belongs in `.env`, which is never uploaded. Then check `ContextLimit` and `Effort`: both depend on the model.

## Good to know

- **JSON is strict.** `true` and `false` in lowercase, text in double quotes `"..."`, a comma between settings but none after the last one, and no comments.
- **Tokens, not characters.** `ContextLimit` is the only size counted in tokens, because a model's window is counted in tokens. The sizes for long tool results (`RESULT_LIMIT` and the others in `config.py`) are counted in characters, so they work the same with every model.