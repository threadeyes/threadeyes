# Privacy

ThreadEyes reads your Claude Code conversation logs, which can contain code, client names and private data. This page says exactly what it does with them. Español: [PRIVACIDAD.md](PRIVACIDAD.md).

**In one line: it runs on your computer, makes no network request, and keeps nothing except two report files you can open and delete.**

## What it reads

- Every `*.jsonl` file under the Claude Code logs folder: `~/.claude/projects`, or the folder you pass with `--logs`, or `CLAUDE_CONFIG_DIR/projects`.
- From each line it looks only at: the thread title (`customTitle`), the working folder (`cwd`), the timestamp, the model name, the token counts (`usage`), and the **name** of each tool the assistant called.
- For shell tools (Bash, PowerShell) it looks at the **first word** of each command, only to tell "running or testing" from "reading". The command itself is not kept.
- To read a line the program loads all of it into memory, so the conversation text passes through memory. It does not look at it, keep it or write it anywhere.
- Optionally, a config file you wrote: `--config FILE`, or `threadeyes.json` in the folder where you run it, or `~/.threadeyes.json`.

## What it saves

Only two files, in the output folder (`threadeyes-output` by default):

- `threadeyes-report.md`
- `threadeyes-panel.html`

They contain: thread names, the last folder name of each working directory, dates, spend as percentages only (of the total or of a normal week, never an amount), model names and the share of tool types (build, test, read, coordinate). They do **not** contain conversation text, commands, file contents or file paths other than the last folder name. Thread and folder names are written as plain text: a name can never turn into a link, an image or code in the report or the panel.

When it finishes, ThreadEyes **prints in the terminal** the exact command to refresh the outputs, with your folders. That command is not saved anywhere; the panel only shows the options, without folders.

**Be careful when you share them or take screenshots:** thread names and folder names can be revealing. Check them first. The demo data in `examples/` is invented.

## What it does not do

- **No network.** It uses only Python's standard library and never opens a connection. The panel loads nothing from the internet: its chart library is included in the file, so the panel works offline.
- **No telemetry, no account, no tracking, no analytics.**
- **No database, cache or history.** Each run reads the logs again and rewrites the two files. The program does not even leave Python's `__pycache__` folder, and the panel stores nothing in your browser.
- **It does not change your logs, your Claude Code settings or any other file.**

## How you can check it

- It is open source (MIT licence): read `threadeyes.py`, `panel.py` and `i18n.py`. Search them for `socket`, `urllib`, `http` and `requests`: there is no network code.
- Run it with the network off. It works the same.
- Open `threadeyes-panel.html` and look at the browser's network tab: no requests.

## If you share your reports

A report is as private as the thread names in it. If you publish one, remove or rename what you would not want to show.

## Removing it

Delete the ThreadEyes folder and the output folder. Nothing else was installed or stored.
