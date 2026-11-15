"""Turn Claude Code session transcripts into one readable, shareable HTML page.

    uv run --with markdown python scripts/export_history.py [--terms=FILE] OUT.html SESSION.jsonl [...]

Keeps: the user's messages, the assistant's replies, and each tool action with its result (long
results collapsed and shortened). Leaves out: hidden reasoning, harness reminders and injected
context, and anything private (REDACT, the private terms file, PRIVATE_TOOL_PATHS). Prints what it removed.
"""
import html
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

import markdown

IST = timezone(timedelta(hours=5, minutes=30))
MAX_RESULT = 1500
MAX_INPUT = 2500

# Text the harness injects into user turns; none of it was typed by the user.
INJECTED = re.compile(
    r"<(system-reminder|local-command-caveat|local-command-stdout|command-message|command-args|"
    r"user-prompt-submit-hook|task-notification|EXTREMELY_IMPORTANT|EXTREMELY-IMPORTANT|SUBAGENT-STOP)\b.*?</\1>",
    re.S)
COMMAND = re.compile(r"<command-name>(.*?)</command-name>", re.S)

# Secrets and email addresses, replaced wherever they appear.
REDACT = [
    # personal mailboxes (free-mail and university domains); public addresses, like a firm's
    # submission address or a commit's co-author line, stay as they are
    (re.compile(r"[\w.+-]+@(?:gmail|yahoo|outlook|hotmail|icloud|proton(?:mail)?)\.[\w.]+|[\w.+-]+@[\w-]+\.ac\.in"), "[email removed]"),
    (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), "[key removed]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "[key removed]"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"), "[key removed]"),
    (re.compile(r"\borg_[A-Za-z0-9]{10,}"), "org_[removed]"),
    (re.compile(r"/home/[A-Za-z0-9_.-]+"), "~"),
]


def load_private_terms(path):
    """Personal terms (an entry number, names of unrelated projects) live in a git-ignored file,
    one per line as `term => replacement`, so this public script never contains them."""
    pairs = []
    try:
        for line in open(path, encoding="utf-8"):
            if "=>" in line and not line.lstrip().startswith("#"):
                term, rep = (x.strip() for x in line.split("=>", 1))
                if term:
                    pairs.append((re.compile(re.escape(term), re.I), rep))
    except FileNotFoundError:
        print(f"note: {path} not found; only generic redaction applied")
    return pairs


PRIVATE = []

# Tool calls that read Claude Code's own memory or project list: results are personal, not build history.
PRIVATE_TOOL_PATHS = re.compile(r"\.claude/projects/[^/\s]*/memory|\.claude/projects/?(\s|$|\"|')|ls -la [~/A-Za-z0-9_.-]*/\.claude")

removed = Counter()


def scrub(text: str) -> str:
    for rx, rep in REDACT + PRIVATE:
        text, n = rx.subn(rep, text)
        removed[rep] += n
    return text


def load(paths):
    seen, entries = set(), []
    for order, p in enumerate(paths):
        for i, line in enumerate(open(p, encoding="utf-8")):
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") not in ("user", "assistant") or d.get("isSidechain") or d.get("uuid") in seen:
                continue
            seen.add(d.get("uuid"))
            entries.append((d.get("timestamp", ""), order, i, d))
    entries.sort(key=lambda e: (e[0], e[1], e[2]))
    return [e[3] for e in entries]


def esc(s):
    return html.escape(s, quote=False)


def md(text):
    return markdown.markdown(esc(text), extensions=["tables", "fenced_code", "sane_lists"])


def clip(text, n):
    return text if len(text) <= n else text[:n] + f"\n… [{len(text) - n:,} more characters not shown]"


def tool_label(name, inp):
    desc = inp.get("description") or ""
    if name == "Bash":
        return desc or "Run a shell command", inp.get("command", "")
    if name in ("Read", "Write", "Edit"):
        return f"{name} {inp.get('file_path', '')}", (inp.get("content") or inp.get("new_string") or "")
    if name == "Workflow":
        return "Workflow (multi-agent script)", inp.get("script", "")
    if name.startswith("mcp__plugin_playwright"):
        return "Browser: " + name.split("__")[-1].replace("browser_", "").replace("_", " "), json.dumps({k: v for k, v in inp.items() if k != "code"}, ensure_ascii=False) + ("\n" + inp["code"] if inp.get("code") else "")
    return name, json.dumps(inp, ensure_ascii=False, indent=1)


def result_text(block):
    c = block.get("content")
    if isinstance(c, list):
        parts = []
        for x in c:
            if x.get("type") == "text":
                parts.append(x["text"])
            elif x.get("type") == "image":
                parts.append("[screenshot]")
        c = "\n".join(parts)
    return str(c or "")


def render(entries):
    out, pending, private_ids = [], {}, set()
    turns = Counter()
    for d in entries:
        msg = d.get("message") or {}
        content = msg.get("content")
        ts = d.get("timestamp", "")
        when = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(IST).strftime("%d %b %H:%M") if ts else ""
        if d["type"] == "user":
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            for b in content or []:
                if b.get("type") == "text":
                    raw = b["text"]
                    cmds = COMMAND.findall(raw)
                    text = INJECTED.sub("", raw)
                    text = COMMAND.sub("", text).strip()
                    if text.startswith("Base directory for this skill:") or text.startswith("[SYSTEM NOTIFICATION") or text.startswith("Tool loaded."):
                        continue
                    if d.get("isMeta") or (not text and not cmds):
                        continue
                    if cmds and not text:
                        out.append(f'<div class="cmd">{esc(when)} · ran <code>{esc(" ".join(c.strip() for c in cmds))}</code></div>')
                        continue
                    turns["user"] += 1
                    out.append(f'<section class="user"><div class="who">User <span>{esc(when)}</span></div>{md(scrub(text))}</section>')
                elif b.get("type") == "image":
                    out.append('<div class="cmd">[user attached an image]</div>')
                elif b.get("type") == "tool_result":
                    tid = b.get("tool_use_id")
                    if tid in private_ids:
                        res = "[private: Claude Code's own memory or project list, not part of this build]"
                        removed["private tool result"] += 1
                    else:
                        res = scrub(result_text(b))
                    i = pending.pop(tid, None)
                    html_res = f'<details class="res"><summary>Result{" (error)" if b.get("is_error") else ""}</summary><pre>{esc(clip(res, MAX_RESULT))}</pre></details>'
                    if i is not None:
                        out[i] = out[i].replace("<!--RESULT-->", html_res)
        else:
            for b in content or []:
                t = b.get("type")
                if t == "text" and b.get("text", "").strip():
                    turns["assistant"] += 1
                    out.append(f'<section class="asst"><div class="who">Claude <span>{esc(when)}</span></div>{md(scrub(b["text"]))}</section>')
                elif t == "tool_use":
                    name, inp = b.get("name", ""), b.get("input") or {}
                    label, body = tool_label(name, inp)
                    if PRIVATE_TOOL_PATHS.search(json.dumps(inp)):
                        private_ids.add(b.get("id"))
                    turns["tool"] += 1
                    out.append(f'<div class="tool"><details><summary><b>{esc(scrub(name))}</b> {esc(scrub(label))}</summary><pre>{esc(clip(scrub(body), MAX_INPUT))}</pre></details><!--RESULT--></div>')
                    pending[b.get("id")] = len(out) - 1
                # "thinking" blocks are the model's hidden reasoning and are not part of the conversation shown to the user
    return "\n".join(o.replace("<!--RESULT-->", "") for o in out), turns


def main():
    global PRIVATE
    args = sys.argv[1:]
    terms_file = "submission/private-terms.txt"
    if args and args[0].startswith("--terms="):
        terms_file = args.pop(0).split("=", 1)[1]
    PRIVATE = load_private_terms(terms_file)
    dst, srcs = args[0], args[1:]
    entries = load(srcs)
    body, turns = render(entries)
    first = entries[0].get("timestamp", "")[:16].replace("T", " ")
    last = entries[-1].get("timestamp", "")[:16].replace("T", " ")
    leaks = {"email": len(re.findall(r"[\w.+-]+@[\w-]+\.(?:com|in|org|net)\b", body)),
             "groq key": len(re.findall(r"gsk_[A-Za-z0-9]{20}", body)), "google key": len(re.findall(r"AIza[0-9A-Za-z_-]{20}", body)),
             "private terms": sum(len(rx.findall(body)) for rx, _ in PRIVATE)}
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>FINN build history</title>
<style>
:root {{ --ink:#14213D; --ink2:#55627A; --line:#D4DBE4; --paper:#EDF0F3; --surface:#fff; --mark:#D99A00; }}
@media (prefers-color-scheme: dark) {{ :root {{ --ink:#E9EDF5; --ink2:#9AA6BD; --line:#2A3855; --paper:#0E1626; --surface:#16213A; }} }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.5 system-ui, sans-serif; }}
main {{ max-width:46rem; margin:0 auto; padding:16px; }}
h1 {{ font-size:24px; margin:8px 0 4px; }} .meta {{ color:var(--ink2); font-size:14px; }}
section {{ background:var(--surface); border-radius:12px; padding:10px 14px; margin:12px 0; overflow-wrap:anywhere; }}
section.user {{ border-left:4px solid var(--mark); }}
.who {{ font-weight:600; font-size:13px; color:var(--ink2); }} .who span {{ font-weight:400; margin-left:6px; }}
.tool {{ margin:4px 0 4px 14px; font-size:13px; }} .tool summary {{ cursor:pointer; color:var(--ink2); padding:3px 0; }}
.res {{ margin-left:14px; }} .cmd {{ color:var(--ink2); font-size:13px; margin:8px 0; }}
pre {{ background:var(--paper); padding:8px; border-radius:8px; overflow:auto; font-size:12px; white-space:pre-wrap; max-height:28rem; }}
table {{ border-collapse:collapse; font-size:14px; display:block; overflow-x:auto; max-width:100%; }}
.tool, summary {{ overflow-wrap:anywhere; }} img {{ max-width:100%; }} td, th {{ border:1px solid var(--line); padding:4px 6px; }}
code {{ font-size:13px; }}
</style></head><body><main>
<h1>FINN: AI build history</h1>
<p class="meta">Claude Code sessions, {esc(first)} to {esc(last)} UTC. {turns['user']} user messages, {turns['assistant']} assistant replies, {turns['tool']} tool actions.
Tool actions and their results are collapsed; long ones are shortened. Hidden model reasoning and harness-injected context are not included.
Personal details (email addresses, an entry number, unrelated projects from Claude Code's memory) are replaced with [removed] notes.</p>
{body}
</main></body></html>"""
    with open(dst, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"wrote {dst}: {len(page)/1e6:.1f} MB, {turns}")
    print("replacements:", {k: v for k, v in removed.items() if v})
    print("left after scrubbing (should all be 0):", leaks)


if __name__ == "__main__":
    main()
