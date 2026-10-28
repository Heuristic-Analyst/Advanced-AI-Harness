# Browser

A real Chromium the agent can use, and you can watch. It is driven by
[agent-browser](https://github.com/vercel-labs/agent-browser); this folder only holds the small command around it.

| What | Where |
|---|---|
| `browser.py` | the `browser` command the agent uses (start, stop, status, more, and every agent-browser command) |
| `tmp/` | everything the browser writes. **Safe to delete whenever the browser is closed** |
| the programs (Chromium, agent-browser, the screen) | `Sandboxes/browser/Containerfile` |
| its settings (4 GB memory, the screen's port) | `Sandboxes/browser/sandbox.json` |
| how the agent uses it | `skills/browser/SKILL.md` |

## Read-only for the agent

`Browser` is a read-only project (`READONLY_PROJECTS` in `config.py`). The agent can mount it and run it, but it
can't change, rename or delete anything in here. The one exception is `tmp/`, the only folder it can write in:

```
tmp/
├── profile/      the browser's profile: cookies, logins, history. delete it to log out everywhere
├── downloads/    what the browser downloaded
├── shots/        screenshots
├── files/        pdfs and pages the agent saved
├── logs/         what the screen and the browser printed, for when something breaks
└── output.json   the last long answer, for `browser more`
```

Like any project, only one instance can have `Browser` mounted at a time, so two browsers never share one profile.

## How it runs

1. The agent opens the `browser` sandbox with the `Browser` project (and its own project, if it works on one).
2. You switch the network on: `/sandbox net on`. Websites need it, and only you can switch it on.
3. `browser start` opens Chromium on a virtual screen. Nothing runs before that, and `browser stop` closes it all.
4. The agent reads pages as text (`browser snapshot -i` lists what can be clicked, as `@e1`, `@e2`, ...) and acts on
   them (`browser click @e2`, `browser fill @e3 "text"`).

## Watching, and taking over

`/sandbox` shows a `view:` link like `http://127.0.0.1:53817`. Open it in your own browser: you see the sandbox's
screen live, and you can click and type in it, e.g. to log in or solve a captcha. The profile keeps that login for
next time.

The link only works on your own computer (127.0.0.1), and stays the same until you close the program. It goes
through podman, not through the network, so it works whether the sandbox's network is on or off.

## Good to know

- **Logins are real.** Whatever you log into here, the agent can use, and so can a web page that tricks the agent.
  Don't log into email, banking or anything you couldn't afford to have misused. To log out of everything: close the
  browser, delete `tmp/profile/`.
- **Long pages** come in parts of 6,000 characters (the harness would otherwise only show the agent a preview).
  `browser more` shows the next part.
- **Captchas and bot walls:** some sites block automated browsers. Solve them yourself through the view link; if a
  site keeps blocking, nothing in here gets around it.
- **Updating agent-browser:** change its version in `Sandboxes/browser/Containerfile`. The next start rebuilds it.
