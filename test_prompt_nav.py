"""Run: python3 test_prompt_nav.py — parsers and prompt matcher against fake session files."""
import importlib.util, json, os, tempfile

spec = importlib.util.spec_from_file_location("pn", os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompt-nav.py"))
pn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pn)


def write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.writelines(json.dumps(r) + "\n" for r in rows)


home = tempfile.mkdtemp()
os.environ["HOME"] = home

write(f"{home}/.claude/projects/-p/s1.jsonl", [
    {"type": "user", "message": {"content": "first prompt"}},
    {"type": "user", "isMeta": True, "message": {"content": "injected"}},
    {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
    {"type": "user", "message": {"content": [{"type": "text", "text": "with image [Image #1]"}, {"type": "image"}]}},
    {"type": "user", "message": {"content": "<command-name>/tui</command-name>\n<command-args>default</command-args>"}},
    {"type": "user", "message": {"content": "<local-command-stdout>out</local-command-stdout>"}},
    {"type": "user", "isSidechain": True, "message": {"content": "subagent prompt"}},
    {"type": "user", "isCompactSummary": True, "message": {"content": "summary of the session"}},
    {"type": "user", "message": {"content": "[Request interrupted by user]"}},
    {"type": "user", "message": {"content": "<task-notification><task-id>x</task-id></task-notification>"}},
    {"type": "user", "message": {"content": "<task>fix tests</task> as written"}},
    {"type": "assistant", "message": {"content": "answer"}},
])
assert pn.claude_prompts({"agent_session": {"value": "s1"}}) == ["first prompt", "with image [Image #1]", "/tui default", "<task>fix tests</task> as written"]

cwd = os.path.realpath(tempfile.mkdtemp())
user = lambda t: {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": t}]}}
write(f"{home}/.codex/sessions/2026/01/01/rollout-a.jsonl", [
    {"type": "session_meta", "payload": {"cwd": cwd, "originator": "codex-tui"}},
    user("# AGENTS.md instructions"), user("<environment_context>"), user("one\ntwo"),
    {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": []}},
])
write(f"{home}/.codex/sessions/2026/01/01/rollout-b.jsonl", [  # newer, but a non-interactive exec run
    {"type": "session_meta", "payload": {"cwd": cwd, "originator": "codex_exec"}}, user("exec prompt"),
])
assert pn.codex_prompts({"foreground_cwd": cwd}) == ["one\ntwo"]
assert pn.codex_prompts({"foreground_cwd": "/elsewhere"}) == []

needle = pn.first_line("one\ntwo")
assert needle == "one"
assert pn.first_line("  a   long\tprompt  \nsecond") == "a long prompt"
assert pn.is_prompt("› one", "› ", needle)              # multi-line prompt: first rendered row matches
assert pn.is_prompt("  ❯ first prompt  ", "❯ ", "first prompt")
assert not pn.is_prompt("❯ first", "› ", "first prompt")   # other agent's marker
assert not pn.is_prompt("❯ ", "❯ ", "first prompt")       # empty composer line
assert not pn.is_prompt("❯ firs", "❯ ", "first prompt")   # too short a prefix to trust
assert pn.is_prompt("❯ a long prompt that wra", "❯ ", "a long prompt that wrapped on screen")  # wrapped row
assert pn.is_prompt("❯ a long prompt that…", "❯ ", "a long prompt that wrapped")   # ellipsized row
assert not pn.is_prompt("❯ yes please do it", "❯ ", "yes")  # short prompt must not match a longer one
assert not pn.is_prompt("❯ ", "❯ ", "")                    # empty needle matches nothing

# 100 rows, 10 visible: row 50 lands second from the top; clamped to the scrollback that exists
assert pn.scroll_offset(100, 10, 50, 90) == 41
assert pn.scroll_offset(100, 10, 0, 90) == 90
assert pn.scroll_offset(100, 10, 99, 90) == 0
print("ok")
