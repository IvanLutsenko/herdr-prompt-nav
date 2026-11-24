#!/usr/bin/env python3
"""Table of contents of your prompts in an agent pane (Claude Code, Codex); Enter scrolls the pane to the prompt.

prompt-nav.py                                 menu (pane entrypoint, target pane in $NAV_TARGET)
prompt-nav.py --jump PANE MARKER NEEDLE [top] scroll PANE until the prompt is on screen
"""
import curses, glob, json, os, re, socket, subprocess, sys, time

HERDR = os.environ.get("HERDR_BIN_PATH", "herdr")
# herdr send-keys has no pageup/ctrl+home names, so raw escape sequences go through send-text
PGUP, PGDN, CTRL_HOME, CTRL_END = "\033[5~", "\033[6~", "\033[1;5H", "\033[1;5F"


def herdr(*args):
    r = subprocess.run([HERDR, *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"herdr {args[0]} {args[1]}: {(r.stderr or r.stdout).strip()}")
    return r.stdout


def pane_info(pane):
    return json.loads(herdr("pane", "get", pane))["result"]["pane"]


def norm(s):
    return " ".join(s.split())


def first_line(prompt):
    # the marker row shows only the prompt's first line (wrapped if long)
    return norm(prompt.strip().splitlines()[0])


def jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                pass  # a half-written last line of a live session log


# user-role records the agents inject themselves, not typed by the user (seen in real session logs)
INJECTED = ("<task-notification>", "<local-command-", "<bash-", "<system-reminder>", "<artifact-content-",
            "<environment_context>", "<user_instructions>", "# AGENTS.md", "[Request interrupted")


def claude_prompts(pane):
    sid = (pane.get("agent_session") or {}).get("value", "-")
    files = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl"))
    out = []
    for e in jsonl(files[0]) if files else []:
        if e.get("type") != "user" or e.get("isMeta") or e.get("isSidechain") or e.get("isCompactSummary"):
            continue
        c = e.get("message", {}).get("content")
        text = c if isinstance(c, str) else " ".join(p.get("text", "") for p in c or [] if p.get("type") == "text")
        m = re.search(r"<command-name>(.*?)</command-name>(?:.*?<command-args>(.*?)</command-args>)?", text, re.S)
        if m:
            text = f"{m.group(1)} {m.group(2) or ''}"
        out.append(text.strip())
    return [t for t in out if t and not t.startswith(INJECTED)]


def codex_prompts(pane):
    # herdr reports no session id for Codex: take the newest interactive session started in the pane's cwd.
    # ponytail: two Codex panes in one directory are not told apart; the latest session wins
    cwd = os.path.realpath(pane.get("foreground_cwd") or pane.get("cwd") or "")
    files = sorted(glob.glob(os.path.expanduser("~/.codex/sessions/*/*/*/rollout-*.jsonl")), key=os.path.getmtime, reverse=True)
    for f in files[:300]:
        meta = next(jsonl(f), {}).get("payload", {})
        if meta.get("originator") == "codex-tui" and os.path.realpath(meta.get("cwd", "")) == cwd:
            out = []
            for e in jsonl(f):
                p = e.get("payload", {})
                if e.get("type") == "response_item" and p.get("role") == "user":
                    out.append(" ".join(c.get("text", "") for c in p.get("content", []) if c.get("type") == "input_text").strip())
            return [t for t in out if t and not t.startswith(INJECTED)]
    return []


AGENTS = {"claude": (claude_prompts, "❯ "), "codex": (codex_prompts, "› ")}


def menu(scr, items):
    curses.curs_set(0)
    curses.use_default_colors()
    sel, top = len(items) - 1, 0
    while True:
        h, w = scr.getmaxyx()
        rows = h - 1
        top = min(max(top, sel - rows + 1), sel)
        scr.erase()
        scr.addnstr(0, 0, f" Prompts ({len(items)}) · ↑↓ select · Enter jump · Esc close", w - 1, curses.A_BOLD)
        for i, it in enumerate(items[top:top + rows]):
            n = top + i
            scr.addnstr(i + 1, 0, f"{n + 1:>3} {norm(it)}", w - 1, curses.A_REVERSE if n == sel else 0)
        k = scr.getch()
        if k in (27, ord("q")):
            return None
        if k in (10, 13, curses.KEY_ENTER):
            return sel
        step = {curses.KEY_UP: -1, ord("k"): -1, curses.KEY_DOWN: 1, ord("j"): 1,
                curses.KEY_PPAGE: -rows, curses.KEY_NPAGE: rows, curses.KEY_HOME: -len(items), curses.KEY_END: len(items)}
        sel = min(max(sel + step.get(k, 0), 0), len(items) - 1)


def is_prompt(line, marker, needle):
    """The row shows the needle whole, or its start when the first line wrapped."""
    line = line.strip()
    if not needle or not line.startswith(marker):
        return False
    shown = norm(line[len(marker):]).rstrip("…")  # a TUI may ellipsize a long row
    return len(shown) >= min(8, len(needle)) and needle.startswith(shown)


def api(method, params):
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(5)
        s.connect(os.environ.get("HERDR_SOCKET_PATH") or os.path.expanduser("~/.config/herdr/herdr.sock"))
        s.sendall((json.dumps({"id": "prompt-nav", "method": method, "params": params}) + "\n").encode())
        reply = json.loads(s.makefile().readline() or "{}")
    if "result" not in reply:
        raise RuntimeError(f"{method}: {reply.get('error', 'no reply')}")


def scroll_offset(n_rows, viewport, row, max_offset):
    """offset_from_bottom that puts `row` (index into all n_rows) second from the top of the viewport."""
    return min(max(n_rows - viewport - row + 1, 0), max_offset)


def jump_scrollback(pane, marker, needle, scroll, from_top):
    # history lives in herdr scrollback (agent renders inline): find the row and scroll herdr to it
    vp = scroll["viewport_rows"]
    rows = herdr("pane", "read", pane, "--source", "recent", "--lines", str(scroll["max_offset_from_bottom"] + vp)).splitlines()
    hits = [i for i, l in enumerate(rows) if is_prompt(l, marker, needle)]
    if not hits:
        return False
    api("pane.scroll", {"pane_id": pane, "offset_from_bottom": scroll_offset(len(rows), vp, hits[0] if from_top else hits[-1], scroll["max_offset_from_bottom"])})
    return True


def jump(pane, marker, needle, from_top=False):
    """Scroll pane until the prompt row is on screen; False when the history ran out first."""
    read = lambda: herdr("pane", "read", pane, "--source", "visible")
    # row 0 of a fullscreen TUI is a sticky header with the current turn's prompt, not the prompt itself
    on_screen = lambda s: any(is_prompt(l, marker, needle) for l in s.splitlines()[1:])
    screen = read()
    if on_screen(screen):  # already visible: send no keys at all
        return True
    scroll = pane_info(pane).get("scroll", {})
    if scroll.get("max_offset_from_bottom", 0) > 0:
        return jump_scrollback(pane, marker, needle, scroll, from_top)
    # fullscreen TUI scrolls itself: page from the nearer end until the prompt is on screen.
    # ponytail: identical prompts are not told apart; the first one met from that end wins
    herdr("pane", "send-text", pane, CTRL_HOME if from_top else CTRL_END)
    time.sleep(0.25)
    prev = None
    for _ in range(800):
        screen = read()
        if on_screen(screen):
            return True
        # ponytail: a page key that changes nothing means the end; two pages of identical output look the same
        if screen == prev:  # unchanged after a page key: render lag or the end — wait and look again
            time.sleep(0.3)
            screen = read()
            if screen == prev:
                return False
            continue
        prev = screen
        herdr("pane", "send-text", pane, PGDN if from_top else PGUP)
        time.sleep(0.04)
    return False


def main():
    if sys.argv[1:2] == ["--jump"]:
        sys.exit(0 if jump(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5:] == ["top"]) else 1)
    target = os.environ.get("NAV_TARGET", "")
    try:
        pane = pane_info(target)
        load, marker = AGENTS.get(pane.get("agent"), (lambda p: [], ""))
        items = load(pane)
        msg = f"No prompts: agent '{pane.get('agent') or 'none'}' is not supported or its session was not found."
        if items:
            pick = curses.wrapper(menu, items)
            msg = None
            if pick is not None:
                # jump from inside the popup: it overlays the pane without resizing it, and a miss stays visible here
                print("Jumping…", flush=True)
                if not jump(target, marker, first_line(items[pick]), pick < len(items) // 2):
                    msg = "Prompt not found on screen: the agent no longer renders it (e.g. compacted away)."
    except Exception as e:
        msg = f"prompt-nav failed: {e}"
    if msg:
        input(f"{msg}\nEnter to close.")
    herdr("plugin", "pane", "close", os.environ.get("HERDR_PANE_ID", ""))


if __name__ == "__main__":
    main()
