# Prompt Nav for herdr

A [herdr](https://herdr.dev) plugin that lists the prompts you sent in an agent pane and jumps to one on Enter.

Long agent sessions are mostly scrolling back to "what did I ask there". Prompt Nav reads the agent's own
session log, shows your prompts in a popup over the pane, and scrolls the pane to the one you pick.

Supported agents: **Claude Code** and **Codex**.

## Install

```sh
herdr plugin install IvanLutsenko/herdr-prompt-nav
```

Bind the action in `~/.config/herdr/config.toml`:

```toml
[[keys.command]]
key = "ctrl+p"
type = "plugin_action"
command = "ivanlutsenko.prompt-nav.open"
```

`ctrl+p` is taken from every pane while bound. In Claude Code and shells it duplicates the Up arrow; pick another key if you rely on it.

Requires `python3` on `PATH` (stdlib only), macOS or Linux.

## Use

Focus an agent pane and press the key. `↑`/`↓` (or `j`/`k`), `PgUp`/`PgDn`, `Home`/`End` to move, `Enter` to jump, `Esc` to close.

## How the jump works

- **Fullscreen TUI** (Claude Code with `"tui": "fullscreen"`, Codex): the agent owns its scrollback, so the plugin sends
  `Ctrl+Home`/`Ctrl+End` and then `PageDown`/`PageUp` from the nearer end, reading the screen after each page until the
  prompt row (`❯ ` for Claude Code, `› ` for Codex) is visible. A long session takes a few seconds; do not type into
  the pane meanwhile.
- **Inline rendering** (Claude Code with `"tui": "default"`): history is in herdr's scrollback, so the plugin finds the
  row and scrolls herdr straight to it with `pane.scroll`, prompt second from the top.

## Limits

- Identical prompts are not told apart: the first match met from the scrolling end wins.
- Codex: herdr reports no session id, so the newest interactive Codex session started in the pane's directory is used.
  Two Codex panes in one directory show the latest session's prompts.
- Records the agents inject as user messages (task notifications, environment context, shell-mode output) are filtered by their known tags.
- Prompts the agent no longer renders (e.g. before `/compact`) are listed but cannot be reached; the jump stops at the
  edge of the history.
- herdr's right-click pane menu cannot list plugin actions, so the entry point is a keybinding
  ([discussion #1722](https://github.com/herdrdev/herdr/discussions/1722)).

## Test

```sh
python3 test_prompt_nav.py
```
