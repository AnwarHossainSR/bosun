#!/usr/bin/env python3
"""bosun usage: the tokens a Claude Code session used, read from its transcript files.

Claude Code writes a session to <config>/projects/<project>/<session id>.jsonl (config: $CLAUDE_CONFIG_DIR, else
~/.claude) and each of its subagents to <session id>/subagents/agent-<id>.jsonl beside it, with the token usage of
each API response. This sums them for the whole session, and since a mark for one run. A subagent's response is
often saved before its final output count, so agent output is a lower bound (shown as "≥"); compactions aren't
saved as responses and are estimated from their recorded size.

  usage.py start                   print a mark (now) and the session so far
  usage.py report --since <mark>   report lines for the run since the mark, the session and the context left

Plan limits (how much of your 5-hour or weekly allowance is left) are not in the transcript: run /usage for them.
Standard library only; Python 3.10+.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path

DEFAULT_WINDOW = 200_000
LARGE_WINDOW = 1_000_000
SLUG_LIMIT = 200  # Claude Code cuts project folder names here and appends a hash
# Models whose window Claude Code's own model table gives as 1M (2.1.240 and 2.1.306); older ones have 200k.
NATIVE_1M = re.compile(r"claude-(?:opus-(?:4-[7-9]|[5-9])|sonnet-[5-9]|haiku-[5-9]|fable|mythos)")
FIELDS = ("input", "cache_write", "cache_read", "output")


def die(msg: str, code: int = 1) -> "None":
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# ----------------------------------------------------------------------------- finding the transcript

def config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def _java_hash(text: str) -> int:
    """The 32-bit string hash Claude Code uses for long project folder names (over UTF-16 code units)."""
    h = 0
    data = text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        h = (h * 31 + int.from_bytes(data[i:i + 2], "little")) & 0xFFFFFFFF
    return h - (1 << 32) if h & 0x80000000 else h


def _base36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if not n:
            return out


def project_slug(path: str) -> str:
    """Claude Code's folder name for a project: every UTF-16 unit that isn't an ASCII letter or digit becomes '-'."""
    slug = "".join(c if c.isascii() and c.isalnum() else ("--" if ord(c) > 0xFFFF else "-") for c in path)
    if len(slug) <= SLUG_LIMIT:
        return slug
    return f"{slug[:SLUG_LIMIT]}-{_base36(abs(_java_hash(path)))}"


def first_cwd(path: Path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for _, line in zip(range(50), fh):
                if '"cwd"' in line:
                    try:
                        return json.loads(line).get("cwd")
                    except json.JSONDecodeError:
                        continue
    except OSError:
        pass
    return None


def find_transcript(explicit=None, session=None, cwd=None) -> Path:
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else die(f"{path} not found")
    projects = config_dir() / "projects"
    if not projects.is_dir():
        die(f"no Claude Code transcripts under {projects}; pass --transcript <path to the session's .jsonl>")
    here = Path(cwd or os.getcwd()).resolve()
    dirs = [projects / project_slug(str(p)) for p in (here, *here.parents)]
    dirs = [d for d in dirs if d.is_dir()]
    session = session or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session:
        for d in dirs + sorted(projects.iterdir()):
            path = d / f"{session}.jsonl"
            if path.is_file():
                return path
        die(f"no transcript for session {session} under {projects} (session persistence off?); "
            "pass --transcript <path to the session's .jsonl>")
    # The current session's transcript is the newest: it was written a moment ago, for this very command.
    for d in dirs:
        newest = max(d.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, default=None)
        if newest:
            return newest
    # Folder named some other way: the newest transcript started in this directory or a parent of it.
    recent = sorted(projects.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
    mine = {os.path.normcase(str(p)) for p in (here, *here.parents)}
    for path in recent:
        started = first_cwd(path)
        if started and os.path.normcase(str(Path(started))) in mine:
            return path
    die(f"no transcript for {here} under {projects}; pass --transcript <path to the session's .jsonl>")


# ----------------------------------------------------------------------------- reading usage

def parse_ts(value):
    if not value:
        return None
    try:
        ts = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=_dt.timezone.utc)


def read_usage(path: Path):
    """One record per API response. A response with several content blocks is written as several lines that share
    its message id; keep the largest counts. A response with no line carrying its stop_reason has only the output
    count from the start of its stream: `final` is false. A compaction is a system line with the size it summarised."""
    records, start = {}, None
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return [], None
    with fh:
        for n, line in enumerate(fh):
            if start is None and '"timestamp"' in line:
                try:
                    start = parse_ts(json.loads(line).get("timestamp"))
                except (json.JSONDecodeError, AttributeError):
                    pass
            if '"compact_boundary"' in line:
                try:
                    entry = json.loads(line)
                    meta = entry.get("compactMetadata") or {}
                    tokens = int(meta.get("preTokens") or 0)
                except (json.JSONDecodeError, AttributeError, TypeError, ValueError):
                    tokens = 0
                if tokens and entry.get("subtype") == "compact_boundary":
                    records[f"compact-{entry.get('uuid') or n}"] = {
                        "ts": parse_ts(entry.get("timestamp")), "model": "", "final": True, "compaction": True,
                        "input": tokens, "cache_write": 0, "cache_read": 0, "output": 0}
                continue
            if '"usage"' not in line or '"assistant"' not in line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict) or entry.get("type") != "assistant":
                continue
            msg = entry.get("message") or {}
            usage = msg.get("usage") if isinstance(msg, dict) else None
            if not isinstance(usage, dict):
                continue
            counts = {
                "input": int(usage.get("input_tokens") or 0),
                "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
                "cache_read": int(usage.get("cache_read_input_tokens") or 0),
                "output": int(usage.get("output_tokens") or 0),
            }
            if not any(counts.values()):
                continue  # synthetic and API-error messages: no tokens
            key = msg.get("id") or entry.get("uuid") or f"line{n}"
            final = msg.get("stop_reason") is not None
            old = records.get(key)
            if old:
                for f in FIELDS:
                    old[f] = max(old[f], counts[f])
                old["final"] = old["final"] or final
            else:
                records[key] = {"ts": parse_ts(entry.get("timestamp")), "model": str(msg.get("model") or ""),
                                "final": final, "compaction": False, **counts}
    return list(records.values()), start


def agent_label(path: Path) -> str:
    meta = path.with_name(path.name[: -len(".jsonl")] + ".meta.json")
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    kind = str(data.get("agentType") or "agent")
    desc = str(data.get("description") or "").strip()
    return f"{kind}: {desc}" if desc else kind


def totals(records):
    out = {f: sum(r[f] for r in records) for f in FIELDS}
    out["total"] = sum(out.values())
    out["output_partial"] = sum(1 for r in records if not r["final"])  # responses whose output is only a lower bound
    out["compaction"] = sum(r["input"] for r in records if r["compaction"])
    return out


def gather(transcript: Path, since=None, window=None):
    main, start = read_usage(transcript)
    agents = []
    folder = transcript.with_suffix("")
    if folder.is_dir():
        for path in sorted(folder.rglob("agent-*.jsonl")):
            recs, _ = read_usage(path)
            if recs:
                agents.append({"label": agent_label(path), "file": str(path), "records": recs})

    def in_run(recs):
        return [r for r in recs if since is None or (r["ts"] and r["ts"] >= since)]

    result = {"transcript": str(transcript), "session_start": start.isoformat() if start else None}
    sess_agents = [{"label": a["label"], **totals(a["records"])} for a in agents]
    result["session"] = {"main": totals(main), "agents": len(agents),
                         "agents_total": sum(a["total"] for a in sess_agents),
                         "agents_output": sum(a["output"] for a in sess_agents),
                         "output_partial": sum(a["output_partial"] for a in sess_agents) + totals(main)["output_partial"]}
    result["session"]["total"] = result["session"]["main"]["total"] + result["session"]["agents_total"]
    if since is not None:
        run_agents = [{"label": a["label"], **totals(in_run(a["records"]))} for a in agents]
        run_agents = [a for a in run_agents if a["total"]]
        run_main = totals(in_run(main))
        both = {f: run_main[f] + sum(a[f] for a in run_agents) for f in (*FIELDS, "output_partial", "compaction")}
        result["run"] = {"since": since.isoformat(), "main": run_main, "agents": len(run_agents),
                         "total": run_main["total"] + sum(a["total"] for a in run_agents), **{f"all_{f}": v for f, v in both.items()},
                         "top": sorted(run_agents, key=lambda a: a["total"], reverse=True)}
    else:
        result["run"] = None
        result["top"] = sorted(sess_agents, key=lambda a: a["total"], reverse=True)
    # Context: what the main session's last response read and wrote, which the next one starts from.
    replies = [r for r in main if r["ts"] and not r["compaction"]]
    last = max(replies, key=lambda r: r["ts"], default=None)
    used = sum(last[f] for f in FIELDS) if last else 0
    peak = max((sum(r[f] for f in FIELDS) for r in replies), default=0)
    if window:
        size, assumed = window, False
    else:
        large = peak > DEFAULT_WINDOW or bool(NATIVE_1M.search((last or {}).get("model", "")))
        size, assumed = (LARGE_WINDOW if large else DEFAULT_WINDOW), True
    result["context"] = {"used": used, "window": size, "window_assumed": assumed}
    return result


# ----------------------------------------------------------------------------- output

def human(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 10_000:
        return f"{n / 1000:.0f}k"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def hhmm(iso) -> str:
    ts = parse_ts(iso)
    return ts.astimezone(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "?"


def context_line(ctx) -> str:
    left = max(0, ctx["window"] - ctx["used"])
    pct = round(100 * ctx["used"] / ctx["window"]) if ctx["window"] else 0
    approx = "~" if ctx["window_assumed"] else ""
    return (f"🧠 **Context:** {human(ctx['used'])} of {approx}{human(ctx['window'])} used ({pct}%), {approx}{human(left)} left"
            " · plan limits left: run `/usage`")


def out(n: int, partial: int) -> str:
    return f"≥{human(n)}" if partial else human(n)


def report_lines(res, agents: int):
    sess = res["session"]
    lines = []
    run = res["run"]
    if run:
        lines.append(f"📊 **Tokens, this run:** {human(run['total'])} across the main session and {run['agents']} agent(s)"
                     f" · output {out(run['all_output'], run['all_output_partial'])}"
                     f" · new input {human(run['all_input'] + run['all_cache_write'])}"
                     f" · cache reads {human(run['all_cache_read'])}"
                     + (f" · compaction ~{human(run['all_compaction'])}" if run["all_compaction"] else ""))
        top = run["top"]
    else:
        top = res["top"]
    lines.append(f"🧾 **Session:** {human(sess['total'])} since {hhmm(res['session_start'])}"
                 f" (main {human(sess['main']['total'])}, {sess['agents']} agent(s) {human(sess['agents_total'])};"
                 f" output {out(sess['main']['output'] + sess['agents_output'], sess['output_partial'])})")
    lines.append(context_line(res["context"]))
    for a in top[:agents]:
        lines.append(f"   - {human(a['total'])} (output {out(a['output'], a['output_partial'])}): {a['label']}")
    if (run or {}).get("all_output_partial") or (not run and sess["output_partial"]):
        lines.append("   ≥: some agent replies were saved before their final output count; `/usage` has the exact totals")
    return lines


def now_mark() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="usage.py", description="Tokens this Claude Code session used, from its "
                                     "transcript files. Plan limits aren't in them: run /usage for those.")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True
    for name, text in (("start", "print a mark (now) to pass to `report --since`, and the session so far"),
                       ("report", "report lines: this run (with --since), the session, and the context left")):
        p = sub.add_parser(name, help=text, description=text)
        p.add_argument("--transcript", help="the session's .jsonl (default: found from this directory)")
        p.add_argument("--session", help="session id (default: $CLAUDE_CODE_SESSION_ID, else the newest transcript)")
        p.add_argument("--json", action="store_true")
        if name == "report":
            p.add_argument("--since", help="the mark `start` printed (ISO time)")
            p.add_argument("--agents", type=int, default=0, metavar="N", help="also list the N agents that used most")
        p.add_argument("--window", type=int, metavar="TOKENS",
                       help="the context window (default: $CLAUDE_CODE_MAX_CONTEXT_TOKENS, else inferred from the model)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # Windows pipes default to the ANSI code page, which can't print emoji
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    window = args.window
    if not window and (os.environ.get("CLAUDE_CODE_MAX_CONTEXT_TOKENS") or "").strip().isdigit():
        window = int(os.environ["CLAUDE_CODE_MAX_CONTEXT_TOKENS"])
    since = None
    if getattr(args, "since", None):
        since = parse_ts(args.since) or die(f"--since expects an ISO time such as 2026-10-23T10:39:02Z, got {args.since!r}", 2)
    transcript = find_transcript(args.transcript, args.session)
    res = gather(transcript, since, window or None)
    if args.command == "start":
        mark = now_mark()
        if args.json:
            print(json.dumps({"mark": mark, "session_total": res["session"]["total"], "context": res["context"],
                              "transcript": res["transcript"]}, separators=(",", ":")))
            return 0
        print(f"mark: {mark}")
        print(f"session so far: {human(res['session']['total'])} tokens ({res['session']['agents']} agent(s)); "
              f"context {human(res['context']['used'])} of {'~' if res['context']['window_assumed'] else ''}"
              f"{human(res['context']['window'])}")
        return 0
    if args.json:
        n = max(args.agents, 0)
        if res["run"]:
            res["run"]["top"] = res["run"]["top"][:n]
        else:
            res["top"] = res["top"][:n]
        print(json.dumps(res, separators=(",", ":"), default=str))
        return 0
    print("\n".join(report_lines(res, max(args.agents, 0))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
