#!/usr/bin/env python3
"""bosun taskboard: a deterministic task-graph tool for parallel agent builds.

The board is a JSON file, usually .bosun/plans/<slug>/tasks.json. It is the
single source of truth for a build: which tasks exist, how they depend on each
other, which files each task owns, and where each task stands. Only the
orchestrating session should write to it. Every write is atomic and serialized
with a lock file, so parallel invocations can't lose updates.

Run `taskboard.py --help` or `taskboard.py schema` for details.
Standard library only; Python 3.10+ (tested in CI on 3.10 and 3.13).
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import os
import re
import signal
import sys
import tempfile
import time
from pathlib import Path

VERSION = "0.2.0"
STATUSES = ("pending", "in_progress", "review", "done", "blocked", "failed", "skipped")
FINISHED = frozenset({"done", "skipped"})
INFLIGHT = frozenset({"in_progress", "review"})
STOPPED = frozenset({"blocked", "failed"})
ROSTER = (
    "architect", "scout", "implementer", "test-engineer", "docs-writer",
    "code-reviewer", "security-reviewer", "verifier", "investigator", "monitor",
)
REPORT_AGENTS = frozenset(
    {"architect", "scout", "code-reviewer", "security-reviewer", "verifier", "investigator", "monitor"}
)
SIZE_WEIGHT = {"S": 1, "M": 2, "L": 3}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
GLOB_CHARS = "*?["
MAX_LISTED_WARNINGS = 25

SCHEMA_DOC = """\
bosun task board (tasks.json), schema v1. Annotated example; real files are plain JSON.

{
  "name": "todo-api",                    // required: plan slug
  "title": "Todo API with auth",         // optional human title
  "version": 1,
  "meta": {                              // optional; the build skill fills most of it
    "openspec_change": "add-todo-api",   // OpenSpec plans: openspec/changes/<id>/ (see below)
    "base_branch": "main", "work_branch": "bosun/todo-api", "base_commit": "<sha>",
    "max_parallel": 4, "isolation": "worktree"
  },
  "tasks": [
    {
      "id": "T01",                       // required, unique: letters, digits, . _ - (max 64)
      "title": "Scaffold API project",   // required, imperative mood
      "description": "What to build and why, constraints, pointers to PLAN.md sections.",
      "agent": "implementer",            // roster name or a custom agent type; default implementer
      "kind": "code",                    // code (merged into the work branch) | report (output only)
      "deps": [],                        // ids that must be done or skipped first
      "files": ["package.json", "src/server.ts", "src/routes/"],
                                         // ownership: files, directories ending in "/", or globs
      "acceptance": ["`npm test` passes", "GET /health returns 200"],
      "spec_refs": ["todo-items#Create todo item"],
                                         // OpenSpec plans: "<capability>#<Requirement name>"
      "size": "M",                       // S (<1h of human work) | M (1-3h) | L (3-6h); split bigger work
      "risk": "low",                     // low | medium | high
      "security_sensitive": false,       // auth, crypto, input parsing, secrets, permissions, payments, PII
      "status": "pending"                // managed by the build loop
    }
  ]
}

Roster agents: architect, scout, implementer, test-engineer, docs-writer, code-reviewer,
security-reviewer, verifier, investigator, monitor (plugin names are bosun:<name>).
Report agents default to kind "report": architect, scout, code-reviewer, security-reviewer,
verifier, investigator, monitor.

The build loop writes: status, assignee, attempts, branch, worktree, commit, summary,
notes, history, started_at, finished_at.

Statuses: pending -> in_progress -> review -> done; also blocked, failed, skipped.
A task is ready when it is pending and every dependency is done or skipped.

OpenSpec plans (meta.openspec_change set): the change in openspec/changes/<id>/ is the spec:
proposal.md (why), specs/<capability>/spec.md (delta requirements with scenarios), design.md
(how) and tasks.md (checklist). Board ids are the tasks.md ids (1.1, 1.2, 2.1, ...), one
board task per tasks.md line. Each task lists the requirements it implements in spec_refs, and
every ADDED or MODIFIED requirement needs at least one task. `spec-check` verifies all of this;
`set --status done` ticks the task in tasks.md and `sync` repairs drift.

Planning rules
 1. One task = one agent session: a coherent change to about 1-8 files that can be tested
    on its own, with acceptance criteria an agent can check by running something.
 2. Contracts first: shared types, interfaces, schemas, API contracts and migrations go in
    early tasks so later tasks can be built in parallel against them.
 3. One owner per file at a time. Tasks that touch the same file must be ordered by deps.
    Hotspots (package manifests, lockfiles, route or DI registries, barrel/index files,
    migrations, global config, CI files) belong to one task, or tasks chained by deps.
 4. Prefer vertical slices that deliver testable behavior. Tests ship inside each task;
    avoid "write all the tests" or "polish everything" tasks at the end.
 5. Keep the graph wide and shallow: aim for at least max_parallel ready tasks most of the
    time and a short critical path. Split long chains.
 6. Retire unknowns early with report tasks (scout or investigator, kind "report") that the
    risky tasks depend on.
 7. Mark security_sensitive honestly. Those tasks get a security-review gate.
 8. Acceptance criteria must be observable: a command, a test name, an HTTP call, a UI
    behavior. Not "works well".
 9. Never present a guess about a library API as fact; write "verify: ..." in the
    description instead.
 10. Directories in "files" end with "/" (or "/**"). Overlap detection is conservative:
    a false conflict only costs parallelism, it never corrupts work.
"""

EXAMPLE_BOARD = {
    "name": "todo-api",
    "title": "Todo API with user accounts",
    "version": 1,
    "meta": {"max_parallel": 3},
    "tasks": [
        {
            "id": "T01", "title": "Scaffold project, tooling and CI", "agent": "implementer",
            "deps": [], "size": "M", "risk": "low",
            "files": ["package.json", "tsconfig.json", "src/server.ts", ".github/workflows/"],
            "acceptance": ["`npm test` runs (0 tests ok)", "`npm run lint` passes",
                           "GET /health returns 200"],
        },
        {
            "id": "T02", "title": "Define shared types and DB schema", "agent": "implementer",
            "deps": ["T01"], "size": "S", "risk": "medium",
            "files": ["src/types/", "src/db/schema.ts", "migrations/"],
            "acceptance": ["migration applies on an empty DB", "types compile"],
        },
        {
            "id": "T03", "title": "User signup and login", "agent": "implementer",
            "deps": ["T02"], "size": "M", "risk": "high", "security_sensitive": True,
            "files": ["src/auth/", "src/routes/auth.ts"],
            "acceptance": ["passwords hashed with argon2id or bcrypt",
                           "auth tests cover bad password and duplicate email"],
        },
        {
            "id": "T04", "title": "Todo CRUD endpoints", "agent": "implementer",
            "deps": ["T02"], "size": "M", "risk": "medium",
            "files": ["src/todos/", "src/routes/todos.ts"],
            "acceptance": ["CRUD tests pass", "users cannot read other users' todos"],
        },
        {
            "id": "T05", "title": "Register routes and auth middleware", "agent": "implementer",
            "deps": ["T03", "T04"], "size": "S", "risk": "medium", "security_sensitive": True,
            "files": ["src/routes/index.ts", "src/middleware/"],
            "acceptance": ["unauthenticated todo requests return 401", "e2e smoke test passes"],
        },
        {
            "id": "T06", "title": "README and API docs", "agent": "docs-writer",
            "deps": ["T05"], "size": "S", "risk": "low",
            "files": ["README.md", "docs/"],
            "acceptance": ["every documented command was run successfully"],
        },
    ],
}


# ----------------------------------------------------------------------------- utils

def die(msg: str, code: int = 1) -> "None":
    print(f"taskboard: error: {msg}", file=sys.stderr)
    sys.exit(code)


def now_iso() -> str:
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


def parse_iso(value):
    if not value:
        return None
    try:
        parsed = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def human_age(start, end=None) -> str:
    begin = parse_iso(start)
    if begin is None:
        return "?"
    finish = parse_iso(end) or _dt.datetime.now(_dt.timezone.utc)
    secs = max(0, int((finish - begin).total_seconds()))
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h{(secs % 3600) // 60:02d}m"
    return f"{secs // 86400}d{(secs % 86400) // 3600}h"


def natural_key(value: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", str(value))]


def emit_json(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def shorten(text: str, width: int) -> str:
    text = str(text)
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


# ----------------------------------------------------------------------------- paths

def norm_path(path) -> str:
    p = str(path).strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    p = p.lstrip("/")
    p = re.sub(r"/{2,}", "/", p)
    if p.endswith("/**"):
        p = p[:-2]
    return p


def is_open(path: str) -> bool:
    """True for a directory ("dir/") or a glob: patterns that can cover many files."""
    return path == "" or path.endswith("/") or any(c in path for c in GLOB_CHARS)


def static_prefix(path: str) -> str:
    cut = [path.find(c) for c in GLOB_CHARS if c in path]
    return path[: min(cut)] if cut else path


def paths_overlap(a, b) -> bool:
    """Conservative overlap test between two ownership entries.

    A false positive only reduces parallelism, so when in doubt we say "overlap".
    """
    a, b = norm_path(a), norm_path(b)
    if a == b:
        return True
    a_open, b_open = is_open(a), is_open(b)
    if not a_open and not b_open:
        return False
    pa = static_prefix(a) if a_open else a
    pb = static_prefix(b) if b_open else b
    if a_open and b_open:
        return pa.startswith(pb) or pb.startswith(pa)
    if a_open:
        return pb.startswith(pa)
    return pa.startswith(pb)


def first_overlap(files_a, files_b):
    for x in files_a:
        for y in files_b:
            if paths_overlap(x, y):
                return x, y
    return None


# ----------------------------------------------------------------------------- task accessors

def status_of(task) -> str:
    return task.get("status") or "pending"


def deps_of(task):
    deps = task.get("deps") or []
    if not isinstance(deps, list):
        return []
    return [str(d) for d in deps if isinstance(d, (str, int))]


def agent_of(task) -> str:
    return str(task.get("agent") or "implementer").strip()


def agent_short(agent: str) -> str:
    return agent.split(":")[-1]


def agent_full(agent: str) -> str:
    if ":" in agent:
        return agent
    return f"bosun:{agent}" if agent in ROSTER else agent


def kind_of(task) -> str:
    kind = task.get("kind")
    if kind in ("code", "report"):
        return kind
    return "report" if agent_short(agent_of(task)) in REPORT_AGENTS else "code"


def files_of(task, strict: bool = False):
    files = task.get("files") or []
    if not isinstance(files, list):
        files = []
    files = [norm_path(f) for f in files if isinstance(f, str) and f.strip()]
    if strict and not files and kind_of(task) == "code":
        return ["**"]  # unknown ownership: treat as owning everything
    return files


def size_weight(task) -> int:
    return SIZE_WEIGHT.get(str(task.get("size") or "M").upper(), 2)


def index_tasks(board):
    return {t["id"]: t for t in board.get("tasks", []) if isinstance(t, dict) and isinstance(t.get("id"), str)}


# ----------------------------------------------------------------------------- graph

def find_cycle(idx):
    """Return a dependency cycle as a list of ids (first == last), or None."""
    color = dict.fromkeys(idx, 0)  # 0 new, 1 on stack, 2 finished
    for root in sorted(idx, key=natural_key):
        if color[root]:
            continue
        color[root] = 1
        path = [root]
        stack = [iter([d for d in deps_of(idx[root]) if d in idx])]
        while stack:
            nxt = next(stack[-1], None)
            if nxt is None:
                color[path.pop()] = 2
                stack.pop()
                continue
            if color[nxt] == 1:
                return path[path.index(nxt):] + [nxt]
            if color[nxt] == 0:
                color[nxt] = 1
                path.append(nxt)
                stack.append(iter([d for d in deps_of(idx[nxt]) if d in idx]))
    return None


def topo_order(idx):
    indegree = dict.fromkeys(idx, 0)
    children = {k: [] for k in idx}
    for key, task in idx.items():
        for dep in deps_of(task):
            if dep in idx:
                indegree[key] += 1
                children[dep].append(key)
    queue = sorted((k for k, v in indegree.items() if v == 0), key=natural_key)
    order = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for child in children[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    return order, children


def priorities(idx):
    """Weighted critical-path height and descendant count per task (higher = schedule first)."""
    order, children = topo_order(idx)
    height, descendants = {}, {}
    for node in reversed(order):
        kids = children[node]
        height[node] = size_weight(idx[node]) + max((height[c] for c in kids), default=0)
        desc = set(kids)
        for child in kids:
            desc |= descendants[child]
        descendants[node] = desc
    for node in idx:  # nodes on a cycle (invalid board) still get a value
        height.setdefault(node, size_weight(idx[node]))
        descendants.setdefault(node, set())
    return height, {k: len(v) for k, v in descendants.items()}, children


def ancestors(idx):
    order, _ = topo_order(idx)
    anc = {}
    for node in order:
        acc = set()
        for dep in deps_of(idx[node]):
            if dep in idx:
                acc.add(dep)
                acc |= anc.get(dep, set())
        anc[node] = acc
    for node in idx:
        anc.setdefault(node, set())
    return anc


def is_ready(task, idx) -> bool:
    if status_of(task) != "pending":
        return False
    return all(d in idx and status_of(idx[d]) in FINISHED for d in deps_of(task))


# ----------------------------------------------------------------------------- validation

def validate_board(board):
    errors, warnings = [], []
    if not isinstance(board, dict):
        return ["board must be a JSON object"], warnings
    if not isinstance(board.get("tasks"), list):
        return ["board must have a 'tasks' array"], warnings
    if not board.get("name"):
        warnings.append("board has no 'name' (plan slug)")
    if not board["tasks"]:
        warnings.append("board has no tasks yet")

    idx = {}
    for i, task in enumerate(board["tasks"]):
        if not isinstance(task, dict):
            errors.append(f"tasks[{i}] is not an object")
            continue
        tid = task.get("id")
        label = tid if isinstance(tid, str) else f"tasks[{i}]"
        if not isinstance(tid, str) or not ID_RE.match(tid):
            errors.append(f"{label}: missing or invalid id {tid!r} (letters, digits, . _ -)")
        elif tid in idx:
            errors.append(f"duplicate task id {tid}")
        else:
            idx[tid] = task
        if not isinstance(task.get("title"), str) or not task.get("title", "").strip():
            errors.append(f"{label}: missing title")
        if status_of(task) not in STATUSES:
            errors.append(f"{label}: invalid status {task.get('status')!r} (expected one of {', '.join(STATUSES)})")
        for field in ("deps", "files", "acceptance", "spec_refs"):
            value = task.get(field, [])
            if value is not None and not isinstance(value, list):
                errors.append(f"{label}: '{field}' must be a list")
            elif value and not all(isinstance(v, (str, int) if field == "deps" else str) for v in value):
                errors.append(f"{label}: '{field}' must contain only strings")
        if task.get("kind") not in (None, "code", "report"):
            errors.append(f"{label}: kind must be 'code' or 'report'")
        if task.get("size") is not None and str(task.get("size")).upper() not in SIZE_WEIGHT:
            warnings.append(f"{label}: size {task.get('size')!r} is not S, M or L (treated as M)")
        agent = agent_of(task)
        if ":" not in agent and agent not in ROSTER:
            warnings.append(f"{label}: agent {agent!r} is not in the bosun roster (fine if it is your own agent)")
        if kind_of(task) == "code":
            if not task.get("acceptance"):
                warnings.append(f"{label}: no acceptance criteria")
            files = files_of(task)
            if not files:
                warnings.append(f"{label}: no files declared, so conflicts with parallel tasks can't be detected")
            elif len(files) > 12:
                warnings.append(f"{label}: owns {len(files)} paths; consider splitting it")
            for f in files:
                if static_prefix(f) == "" and is_open(f):
                    warnings.append(f"{label}: pattern {f!r} covers the whole repo, so this task will run alone")
        if str(task.get("size") or "").upper() == "L" and task.get("risk") == "high":
            warnings.append(f"{label}: large and high-risk; consider a spike task or a split")

    for tid, task in idx.items():
        for dep in deps_of(task):
            if dep == tid:
                errors.append(f"{tid}: depends on itself")
            elif dep not in idx:
                errors.append(f"{tid}: unknown dependency {dep}")

    cycle = find_cycle(idx)
    if cycle:
        errors.append("dependency cycle: " + " -> ".join(cycle) + " (each task needs the next)")
        return errors, warnings

    anc = ancestors(idx)
    overlap_warnings = []
    keys = sorted(idx, key=natural_key)
    for i, a in enumerate(keys):
        if kind_of(idx[a]) != "code":
            continue
        for b in keys[i + 1:]:
            if kind_of(idx[b]) != "code" or a in anc[b] or b in anc[a]:
                continue
            hit = first_overlap(files_of(idx[a]), files_of(idx[b]))
            if hit:
                overlap_warnings.append(
                    f"{a} and {b} both own {hit[0]!r}/{hit[1]!r} but neither depends on the other: "
                    "they will be serialized at runtime; add a dep if order matters")
    if len(overlap_warnings) > MAX_LISTED_WARNINGS:
        extra = len(overlap_warnings) - MAX_LISTED_WARNINGS
        overlap_warnings = overlap_warnings[:MAX_LISTED_WARNINGS] + [f"... and {extra} more overlap warnings"]
    warnings.extend(overlap_warnings)

    for tid, task in idx.items():
        if status_of(task) in FINISHED | INFLIGHT:
            unfinished = [d for d in deps_of(task) if d in idx and status_of(idx[d]) not in FINISHED]
            if unfinished:
                warnings.append(f"{tid} is {status_of(task)} but its deps {', '.join(unfinished)} are not finished")
    return errors, warnings


# ----------------------------------------------------------------------------- storage

def find_project_root(start=None) -> Path:
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here] + list(here.parents):
        if (candidate / ".bosun").is_dir() or (candidate / ".git").exists():
            return candidate
    return here


def bosun_dir_for(board_path: Path) -> Path:
    for parent in board_path.resolve().parents:
        if parent.name == ".bosun":
            return parent
    return find_project_root(board_path.parent) / ".bosun"


def resolve_board(ref: str) -> Path:
    path = Path(ref)
    if path.is_file():
        return path
    if path.is_dir() and (path / "tasks.json").is_file():
        return path / "tasks.json"
    slug_path = find_project_root() / ".bosun" / "plans" / ref / "tasks.json"
    if slug_path.is_file():
        return slug_path
    die(f"board not found: {ref!r} (give a tasks.json path, a plan directory, or a plan slug)")
    raise AssertionError  # unreachable


def latest_board(root=None):
    plans = (Path(root) if root else find_project_root()) / ".bosun" / "plans"
    boards = sorted(plans.glob("*/tasks.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return boards[0] if boards else None


def load_board(path: Path):
    try:
        with open(path, encoding="utf-8") as fh:
            board = json.load(fh)
    except json.JSONDecodeError as exc:
        die(f"{path}: invalid JSON: {exc}")
    except OSError as exc:
        die(f"{path}: {exc}")
    if not isinstance(board, dict) or not isinstance(board.get("tasks"), list):
        die(f"{path}: a board must be a JSON object with a 'tasks' array")
    return board


def save_board(path: Path, board) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".tasks.", suffix=".tmp", dir=str(path.resolve().parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(board, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


@contextlib.contextmanager
def board_lock(path: Path, timeout: float = 20.0, stale_after: float = 120.0):
    lock = str(path) + ".lock"
    started = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > stale_after:
                    os.remove(lock)
                    continue
            except OSError:
                continue
            if time.time() - started > timeout:
                die(f"board is locked by another process ({lock}); delete the lock file if nothing else is running")
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            os.remove(lock)


def read_config(board_path: Path):
    cfg_path = bosun_dir_for(board_path) / "config.json"
    try:
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def default_parallel(board, board_path: Path) -> int:
    for value in (
        (board.get("meta") or {}).get("max_parallel"),
        ((read_config(board_path).get("build") or {}).get("max_parallel")),
    ):
        if isinstance(value, int) and value > 0:
            return value
    return 4


def write_text_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.resolve().parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        with contextlib.suppress(OSError):
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, str(path))
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


# ----------------------------------------------------------------------------- openspec
# A plan can be an OpenSpec change (github.com/Fission-AI/OpenSpec): openspec/changes/<id>/
# holds proposal.md, delta specs (specs/<capability>/spec.md), design.md and tasks.md. The
# board then uses the task ids of tasks.md and links each task to the requirements it
# implements through spec_refs. The readers below follow the OpenSpec 1.x formats closely
# enough for bosun's cross-checks; `openspec validate --strict` stays the authority.

OS_TASK_RE = re.compile(r"^(\s*(?:[-*+]|\d{1,9}[.)])\s*\[)([^\]]*)\](.*)$")
OS_TASK_ID = re.compile(r"^(\d+(?:\.\d+)+(?:[A-Za-z]+)?)(?=\s|$)")
OS_H2_ANY = re.compile(r"^ {0,3}##(?!#)(?:[ \t]+|[ \t]*$)")
OS_GROUP = re.compile(r"^ {0,3}##[ \t]+(\d+)\.(?:[ \t]|$)")
OS_REQ = re.compile(r"^###\s*Requirement:\s*(.+)\s*$", re.IGNORECASE)
OS_SECTION = re.compile(r"^##\s+(.+)$")
OS_FENCE_OPEN = re.compile(r"^\s*(`{3,}|~{3,})")
OS_FENCE_CLOSE = re.compile(r"^\s*(`{3,}|~{3,})\s*$")
DELTA_SECTIONS = {"added requirements": "added", "modified requirements": "modified",
                  "removed requirements": "removed", "renamed requirements": "renamed"}
REQ_TEXT_MAX = 500
WHY_MIN, WHY_MAX, PURPOSE_MIN, DELTAS_MAX = 50, 1000, 50, 10
BRIEF_SPEC_CHARS = 8000


def group_number(value: str) -> str:
    return re.sub(r"^0+(?=\d)", "", value)


def os_task(line: str):
    """(prefix, mark, rest) for a tasks.md checkbox line, else None (OpenSpec's task-line rules)."""
    m = OS_TASK_RE.match(line)
    if not m:
        return None
    inner, rest = m.group(2), m.group(3)
    mark = inner.strip()
    if len(mark) > 1:
        return None
    if rest[:1] in ("(", "[") and not (inner and not mark):
        return None  # a link such as "- [x](url)", not a task
    return m.group(1), inner, rest


def parse_tasks_md(text: str):
    """Task lines of a tasks.md in order: {id, done, text, line, group}. id is None when absent."""
    tasks, group = [], None
    for number, line in enumerate(re.split(r"\r?\n", text), 1):
        if OS_H2_ANY.match(line):
            g = OS_GROUP.match(line)
            group = g.group(1) if g else None
            continue
        parsed = os_task(line)
        if not parsed:
            continue
        desc = parsed[2].strip()
        m = OS_TASK_ID.match(desc)
        tasks.append({"id": m.group(1) if m else None, "done": parsed[1].strip().lower() == "x",
                      "text": desc[m.end():].strip() if m else desc, "line": number, "group": group})
    return tasks


def mark_tasks_md(path: Path, wanted, dry_run: bool = False):
    """Tick (True) or untick (False) task lines by id. Returns (changed ids, ids with no line)."""
    with open(path, encoding="utf-8", newline="") as fh:
        lines = fh.read().splitlines(keepends=True)
    changed, seen = [], set()
    for i, raw in enumerate(lines):
        body = raw.rstrip("\r\n")
        parsed = os_task(body)
        m = OS_TASK_ID.match(parsed[2].strip()) if parsed else None
        if not m or m.group(1) not in wanted:
            continue
        tid = m.group(1)
        seen.add(tid)
        if (parsed[1].strip().lower() == "x") == wanted[tid]:
            continue
        lines[i] = parsed[0] + ("x" if wanted[tid] else " ") + "]" + parsed[2] + raw[len(body):]
        if tid not in changed:
            changed.append(tid)
    if changed and not dry_run:
        write_text_atomic(path, "".join(lines))
    return changed, [t for t in wanted if t not in seen]


def append_task_line(path: Path, tid: str, title: str) -> None:
    """Add "- [ ] <id> <title>" to the end of group N of tasks.md (N = the id's first number)."""
    with open(path, encoding="utf-8", newline="") as fh:
        text = fh.read()
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = re.split(r"\r?\n", text)
    group = group_number(tid.split(".")[0])
    insert_at, in_group, follow_up = None, False, None
    for i, line in enumerate(lines):
        if OS_H2_ANY.match(line):
            g = OS_GROUP.match(line)
            in_group = bool(g) and group_number(g.group(1)) == group
            if in_group:
                insert_at = i + 1
            elif follow_up is None and re.match(r"^ {0,3}##[ \t]+workflow follow-up[ \t]*$", line, re.IGNORECASE):
                follow_up = i
            continue
        if in_group and os_task(line):
            insert_at = i + 1
    entry = f"- [ ] {tid} {title}"
    if insert_at is not None:
        lines.insert(insert_at, entry)
    else:  # new group, kept before an optional "## Workflow follow-up" section
        at = follow_up if follow_up is not None else len(lines)
        while at > 0 and not lines[at - 1].strip():
            at -= 1
        gap = follow_up is not None and at == follow_up  # no blank line left before the follow-up section
        lines[at:at] = ["", f"## {group}. Follow-up", "", entry] + ([""] if gap else [])
    write_text_atomic(path, newline.join(lines).rstrip("\r\n") + newline)


def md_lines(text: str):
    return text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def fence_mask(lines):
    """True for lines inside fenced code blocks (fence lines included)."""
    mask, active = [False] * len(lines), None
    for i, line in enumerate(lines):
        if active is None:
            m = OS_FENCE_OPEN.match(line)
            if m:
                active = (m.group(1)[0], len(m.group(1)))
                mask[i] = True
            continue
        mask[i] = True
        m = OS_FENCE_CLOSE.match(line)
        if m and m.group(1)[0] == active[0] and len(m.group(1)) >= active[1]:
            active = None
    return mask


def md_sections(lines, mask):
    """[(title, body_start, body_end)] for every unfenced "## " section."""
    heads = []
    for i, line in enumerate(lines):
        m = None if mask[i] else OS_SECTION.match(line)
        if m:
            heads.append((i, m.group(1).strip()))
    return [(title, i + 1, heads[n + 1][0] if n + 1 < len(heads) else len(lines))
            for n, (i, title) in enumerate(heads)]


def req_name(raw: str) -> str:
    return re.sub(r"[ \t]+#+[ \t]*$", "", raw).strip()


def requirement_block(name, block, bmask, path, line, section):
    body, bm = block[1:], bmask[1:]
    text, metadata = [], []
    for raw, fenced in zip(body, bm):
        if fenced:
            continue
        if re.match(r"^#{1,6}\s", raw):
            break
        stripped = raw.strip()
        if stripped:
            (metadata if re.match(r"^\*\*[^*]+\*\*:", stripped) else text).append(stripped)
    scenarios, empty = [], 0
    for k, raw in enumerate(body):
        if bm[k] or not re.match(r"^####\s+", raw):
            continue
        end = k + 1
        while end < len(body) and (bm[end] or not re.match(r"^#{1,4}\s", body[end])):
            end += 1
        if "\n".join(body[k + 1:end]).strip():
            scenarios.append(re.sub(r"^####\s+(?:Scenario:\s*)?", "", raw, flags=re.IGNORECASE).strip())
        else:
            empty += 1
    misleveled = sum(1 for raw, fenced in zip(body, bm)
                     if not fenced and re.match(r"^#{1,3}\s*Scenario\b", raw, re.IGNORECASE))
    return {"name": name, "section": section, "path": path, "line": line,
            "text": "\n".join(text or metadata), "scenarios": scenarios, "empty_scenarios": empty,
            "misleveled_scenarios": misleveled, "raw": "\n".join(block).rstrip()}


def requirement_blocks(lines, mask, start, end, path, section):
    blocks, i = [], start
    while i < end:
        m = None if mask[i] else OS_REQ.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < end and (mask[j] or not OS_REQ.match(lines[j])):
            j += 1
        blocks.append(requirement_block(req_name(m.group(1)), lines[i:j], mask[i:j], path, i + 1, section))
        i = j
    return blocks


def section_text(lines, mask, start, end) -> str:
    return "\n".join(lines[i] for i in range(start, end)).strip()


def parse_main_spec(text: str, path: str):
    lines = md_lines(text)
    mask = fence_mask(lines)
    spec = {"purpose": "", "requirements": {}}
    for title, start, end in md_sections(lines, mask):
        if title.lower() == "requirements":
            for block in requirement_blocks(lines, mask, start, end, path, "main"):
                spec["requirements"].setdefault(block["name"], block)
        elif title.lower() == "purpose":
            spec["purpose"] = section_text(lines, mask, start, end)
    return spec


def parse_delta(text: str, path: str):
    """Parse a delta spec: ADDED/MODIFIED blocks, REMOVED entries, RENAMED pairs, plus mistakes."""
    lines = md_lines(text)
    mask = fence_mask(lines)
    sections = md_sections(lines, mask)
    delta = {"path": path, "purpose": None, "added": [], "modified": [], "removed": [], "renamed": [],
             "present": set(), "unpaired": [], "orphans": [], "stray_text": []}
    # comments blanked out, fenced text kept: what OpenSpec's archive would silently drop
    plain = "\n".join("" if mask[i] else line for i, line in enumerate(lines))
    plain = re.sub(r"<!--[\s\S]*?(?:--!?>|\Z)", lambda m: re.sub(r"[^\n]", " ", m.group(0)), plain).split("\n")
    visible = [lines[i] if mask[i] else plain[i] for i in range(len(lines))]
    first = sections[0][1] - 1 if sections else len(lines)
    delta["orphans"] += requirement_blocks(lines, mask, 0, first, path, "orphan")
    if any(visible[i].strip() and not re.match(r"^#\s", visible[i]) for i in range(first)):
        delta["stray_text"].append("text above the first '## ' section")
    for title, start, end in sections:
        key = title.lower()
        kind = DELTA_SECTIONS.get(key)
        if kind:
            delta["present"].add(kind)
        if kind in ("added", "modified"):
            delta[kind] += requirement_blocks(lines, mask, start, end, path, kind)
            stop = next((i for i in range(start, end) if not mask[i] and OS_REQ.match(lines[i])), end)
            if any(visible[i].strip() and not re.match(r"^###\s", visible[i]) for i in range(start, stop)):
                delta["stray_text"].append(f"text before the first requirement in '## {title}'")
        elif kind == "removed":
            for block in requirement_blocks(lines, mask, start, end, path, "removed"):
                block["reason"] = bool(re.search(r"\*\*Reason\*\*", block["raw"]))
                block["migration"] = bool(re.search(r"\*\*Migration\*\*", block["raw"]))
                delta["removed"].append(block)
            for i in range(start, end):
                m = None if mask[i] else re.match(r"^\s*[-*+]\s*`?###\s*Requirement:\s*(.+?)`?\s*$", lines[i])
                if m:
                    delta["removed"].append({"name": req_name(m.group(1)), "section": "removed", "path": path,
                                             "line": i + 1, "raw": lines[i].strip(), "bullet": True})
        elif kind == "renamed":
            pending = None
            for i in range(start, end):
                if mask[i]:
                    continue
                f = re.match(r"^\s*[-*+]?\s*FROM:\s*`?###\s*Requirement:\s*(.+?)`?\s*$", lines[i])
                t = re.match(r"^\s*[-*+]?\s*TO:\s*`?###\s*Requirement:\s*(.+?)`?\s*$", lines[i])
                if f:
                    if pending:
                        delta["unpaired"].append(("FROM", pending[0]))
                    pending = (req_name(f.group(1)), i + 1)
                elif t and pending:
                    delta["renamed"].append({"from": pending[0], "to": req_name(t.group(1)), "line": pending[1]})
                    pending = None
                elif t:
                    delta["unpaired"].append(("TO", req_name(t.group(1))))
            if pending:
                delta["unpaired"].append(("FROM", pending[0]))
        elif key == "purpose":
            delta["purpose"] = section_text(lines, mask, start, end)
        else:
            delta["orphans"] += requirement_blocks(lines, mask, start, end, path, "orphan")
            if any(visible[i].strip() for i in range(start, end)):
                delta["stray_text"].append(f"section '## {title}'")
    return delta


def read_text(path: Path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def openspec_change(board, board_path: Path):
    """Locate the OpenSpec change linked by meta.openspec_change, or None for a classic plan."""
    meta = board.get("meta") or {}
    change_id = meta.get("openspec_change")
    if not change_id:
        return None
    if not isinstance(change_id, str) or not ID_RE.match(change_id):
        die(f"meta.openspec_change {change_id!r} is not a valid change id")
    root = bosun_dir_for(board_path).parent
    planning = read_config(board_path).get("planning")
    base = Path(str(meta.get("openspec_dir") or (planning.get("openspec_dir") if isinstance(planning, dict) else None)
                    or "openspec"))
    base = base if base.is_absolute() else root / base
    change_dir = base / "changes" / change_id
    archived = None
    if not change_dir.is_dir():
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-" + re.escape(change_id) + "$")
        found = sorted(p for p in (base / "changes" / "archive").glob(f"*-{change_id}") if pattern.match(p.name))
        archived = found[-1] if found else None
    return {"id": change_id, "base": base, "dir": change_dir, "tasks_md": change_dir / "tasks.md",
            "archived": archived}


def load_change(info):
    """Read proposal, tasks.md and every delta spec (with its main spec, if any) of a change."""
    change = dict(info, proposal=read_text(info["dir"] / "proposal.md"), tasks_text=read_text(info["tasks_md"]),
                  meta_text=read_text(info["dir"] / ".openspec.yaml"), deltas=[], root_spec=False)
    specs_dir = info["dir"] / "specs"
    change["root_spec"] = (specs_dir / "spec.md").is_file()
    if specs_dir.is_dir():
        for spec in sorted(specs_dir.rglob("spec.md"), key=lambda p: p.as_posix()):
            if not spec.is_file() or spec.parent == specs_dir:
                continue
            capability = spec.parent.relative_to(specs_dir).as_posix()
            delta = parse_delta(read_text(spec) or "", f"specs/{capability}/spec.md")
            delta["capability"] = capability
            main_text = read_text(info["base"] / "specs" / capability / "spec.md")
            delta["main"] = parse_main_spec(main_text, capability) if main_text is not None else None
            change["deltas"].append(delta)
    change["skip_specs"] = bool(re.search(r"(?m)^skip_specs:\s*true\s*(#.*)?$", change["meta_text"] or "",
                                          re.IGNORECASE))
    return change


def spec_requirements(change):
    """{"<capability>#<name>": requirement} for everything a task may reference."""
    out = {}
    for delta in change["deltas"]:
        for kind in ("added", "modified", "removed"):
            for req in delta[kind]:
                out.setdefault(f"{delta['capability']}#{req['name']}", req)
        for pair in delta["renamed"]:
            out.setdefault(f"{delta['capability']}#{pair['to']}",
                           {"name": pair["to"], "section": "renamed", "path": delta["path"], "line": pair["line"],
                            "raw": f"RENAMED FROM: {pair['from']} TO: {pair['to']}", "scenarios": []})
    return out


def spec_refs_of(task):
    refs = task.get("spec_refs") or []
    return [r.strip() for r in refs if isinstance(r, str) and r.strip()] if isinstance(refs, list) else []


def proposal_sections(text: str):
    lines = md_lines(text)
    mask = fence_mask(lines)
    return {title.lower(): section_text(lines, mask, start, end) for title, start, end in md_sections(lines, mask)}


def spec_check(board, board_path: Path):
    """Cross-check a board against its OpenSpec change. Returns (errors, warnings, report)."""
    info = openspec_change(board, board_path)
    if info is None:
        return ["board has no meta.openspec_change, so it is not linked to an OpenSpec change"], [], {}
    if not info["dir"].is_dir():
        where = f"; it was archived to {info['archived']}" if info["archived"] else ""
        return [f"change directory not found: {info['dir']}{where}"], [], {"change": info["id"]}
    change = load_change(info)
    errors, warnings = [], []
    report = {"change": info["id"], "dir": str(info["dir"]), "requirements": 0, "coverage": {}, "uncovered": [],
              "tasks_md": {"total": 0, "ticked": 0}}

    # proposal.md (openspec archive only warns about these; bosun reports them the same way)
    if change["proposal"] is None:
        errors.append("proposal.md is missing")
    else:
        sections = proposal_sections(change["proposal"])
        why = sections.get("why", "")
        if not why:
            warnings.append("proposal.md: '## Why' is missing or empty")
        elif not WHY_MIN <= len(why) <= WHY_MAX:
            warnings.append(f"proposal.md: '## Why' has {len(why)} characters; OpenSpec expects {WHY_MIN}-{WHY_MAX}")
        if not sections.get("what changes"):
            warnings.append("proposal.md: '## What Changes' is missing or empty")

    # delta specs
    if change["root_spec"]:
        errors.append("specs/spec.md has no capability folder; move it to specs/<capability>/spec.md")
    if change["skip_specs"] and change["deltas"]:
        errors.append("skip_specs is set in .openspec.yaml but spec files exist under specs/")
    deltas_total = 0
    for delta in change["deltas"]:
        where = delta["path"]
        main = delta["main"]
        entries = sum(len(delta[k]) for k in ("added", "modified", "removed", "renamed"))
        deltas_total += entries
        if not delta["present"]:
            errors.append(f"{where}: no delta sections (## ADDED/MODIFIED/REMOVED/RENAMED Requirements)")
        elif not entries:
            errors.append(f"{where}: delta sections contain no '### Requirement:' entries")
        for text in delta["stray_text"]:
            errors.append(f"{where}: {text} is not carried into the main spec by archive; "
                          "move it into a requirement, proposal.md or design.md")
        for orphan in delta["orphans"]:
            errors.append(f"{where}:{orphan['line']}: requirement {orphan['name']!r} is outside the delta sections")
        for side, name in delta["unpaired"]:
            errors.append(f"{where}: RENAMED {side}: {name!r} has no matching {'TO' if side == 'FROM' else 'FROM'}: line")
        seen = {}
        for kind in ("added", "modified"):
            for req in delta[kind]:
                label = f"{where}:{req['line']}: {kind.upper()} {req['name']!r}"
                if req["name"] in seen.get(kind, set()):
                    errors.append(f"{label} is duplicated")
                seen.setdefault(kind, set()).add(req["name"])
                if not req["text"]:
                    errors.append(f"{label} has no requirement text")
                elif not re.search(r"\b(SHALL|MUST)\b", req["text"]):
                    errors.append(f"{label}: requirement text needs SHALL or MUST")
                if kind == "added" and len(req["text"]) > REQ_TEXT_MAX:
                    errors.append(f"{label}: requirement text is {len(req['text'])} characters (max {REQ_TEXT_MAX}); "
                                  "move detail into scenarios or split it")
                if not req["scenarios"]:
                    hint = " (scenarios need exactly four #: '#### Scenario: ...')" \
                        if req["misleveled_scenarios"] or req["empty_scenarios"] else ""
                    errors.append(f"{label} needs at least one '#### Scenario:' with content{hint}")
        names = {k: {r["name"] for r in delta[k]} for k in ("added", "modified", "removed")}
        for a, b in (("added", "modified"), ("added", "removed"), ("modified", "removed")):
            for name in sorted(names[a] & names[b]):
                errors.append(f"{where}: {name!r} is in both {a.upper()} and {b.upper()}")
        renamed_to = {p["to"] for p in delta["renamed"]}
        if main is None:
            if delta["modified"] or delta["removed"] or delta["renamed"]:
                errors.append(f"{where}: capability {delta['capability']!r} has no main spec yet, "
                              "so it can only ADD requirements")
            if len((delta["purpose"] or "").strip()) < PURPOSE_MIN:
                warnings.append(f"{where}: new capability without a '## Purpose' of {PURPOSE_MIN}+ characters; "
                                "archive would write a TBD placeholder")
        else:
            if delta["purpose"]:
                warnings.append(f"{where}: '## Purpose' in a delta is used only when a capability is created; "
                                "edit the main spec's Purpose instead")
            existing = set(main["requirements"])
            for req in delta["added"]:
                if req["name"] in existing:
                    errors.append(f"{where}: ADDED {req['name']!r} already exists in the main spec "
                                  "(archive would refuse); use MODIFIED")
            for req in delta["modified"]:
                current = main["requirements"].get(req["name"])
                if current is None and req["name"] not in renamed_to:
                    errors.append(f"{where}: MODIFIED {req['name']!r} does not exist in the main spec "
                                  "(archive would refuse)")
                elif current is not None:
                    lost = list(current["scenarios"])
                    for name in req["scenarios"]:
                        if name in lost:
                            lost.remove(name)
                    if lost:
                        errors.append(f"{where}: MODIFIED {req['name']!r} drops scenario(s) "
                                      f"{', '.join(repr(s) for s in lost)}; MODIFIED replaces the whole block and "
                                      "archive refuses to drop scenarios, so copy them in")
            for req in delta["removed"]:
                if req["name"] not in existing:
                    warnings.append(f"{where}: REMOVED {req['name']!r} does not exist in the main spec, "
                                    "so archive removes nothing")
                elif not req.get("bullet") and not (req.get("reason") and req.get("migration")):
                    warnings.append(f"{where}: REMOVED {req['name']!r} should state **Reason** and **Migration**")
            for pair in delta["renamed"]:
                if pair["from"] not in existing:
                    errors.append(f"{where}: RENAMED FROM {pair['from']!r} does not exist in the main spec "
                                  "(archive would refuse)")
                if pair["to"] in existing:
                    errors.append(f"{where}: RENAMED TO {pair['to']!r} already exists in the main spec "
                                  "(archive would refuse)")
    if not change["deltas"] and not change["skip_specs"] and not change["root_spec"]:
        errors.append("no delta specs under specs/; add specs/<capability>/spec.md, "
                      "or set skip_specs: true in .openspec.yaml for a change with no behavior change")
    if deltas_total > DELTAS_MAX:
        warnings.append(f"{deltas_total} requirement deltas; OpenSpec suggests splitting changes with more than "
                        f"{DELTAS_MAX} (archive shows a warning)")

    # board <-> requirements
    idx = index_tasks(board)
    reqs = spec_requirements(change)
    lowered = {k.lower(): k for k in reqs}
    report["requirements"] = len(reqs)
    for tid in sorted(idx, key=natural_key):
        for ref in spec_refs_of(idx[tid]):
            if ref in reqs:
                report["coverage"].setdefault(ref, []).append(tid)
            elif "#" not in ref:
                errors.append(f"{tid}: spec_ref {ref!r} must look like '<capability>#<Requirement name>'")
            else:
                hint = f" (did you mean {lowered[ref.lower()]!r}?)" if ref.lower() in lowered else ""
                errors.append(f"{tid}: spec_ref {ref!r} matches no requirement in the change{hint}")
    for ref, req in reqs.items():
        if ref in report["coverage"]:
            continue
        if req["section"] in ("added", "modified"):
            report["uncovered"].append(ref)
            errors.append(f"requirement {ref!r} ({req['section'].upper()}) is not covered by any task's spec_refs")
        elif req["section"] == "removed":
            warnings.append(f"REMOVED requirement {ref!r} has no task removing the behavior")

    # board <-> tasks.md
    if change["tasks_text"] is None:
        errors.append("tasks.md is missing")
    else:
        lines = parse_tasks_md(change["tasks_text"])
        report["tasks_md"] = {"total": len(lines), "ticked": sum(1 for t in lines if t["done"])}
        listed = {}
        for entry in lines:
            if entry["id"] is None:
                warnings.append(f"tasks.md:{entry['line']}: task line without an id ('- [ ] N.M ...'); "
                                "bosun cannot track it")
            elif entry["id"] in listed:
                errors.append(f"tasks.md:{entry['line']}: task id {entry['id']} appears twice")
            else:
                listed[entry["id"]] = entry
                if entry["group"] and group_number(entry["id"].split(".")[0]) != group_number(entry["group"]):
                    errors.append(f"tasks.md:{entry['line']}: task {entry['id']} sits under group {entry['group']}")
        for tid in sorted(set(listed) - set(idx), key=natural_key):
            errors.append(f"tasks.md task {tid} is not on the board, so the build would never run it")
        for tid in sorted(set(idx) - set(listed), key=natural_key):
            errors.append(f"board task {tid} has no line in tasks.md")
        stale = [tid for tid in sorted(set(idx) & set(listed), key=natural_key)
                 if status_of(idx[tid]) != "skipped" and listed[tid]["done"] != (status_of(idx[tid]) == "done")]
        if stale:
            warnings.append(f"tasks.md checkboxes differ from the board for {', '.join(stale)}; run `sync`")
    return errors, warnings, report


def tick_tasks_md(board, board_path: Path, wanted) -> None:
    """Mirror board status changes into tasks.md for OpenSpec plans; never fails the caller."""
    info = openspec_change(board, board_path)
    if info is None or not wanted:
        return
    if not info["tasks_md"].is_file():
        why = f"the change was archived to {info['archived']}" if info["archived"] else f"{info['tasks_md']} not found"
        print(f"note: {why}; tasks.md checkboxes not updated", file=sys.stderr)
        return
    changed, missing = mark_tasks_md(info["tasks_md"], wanted)
    for tid in changed:
        print(f"{'ticked' if wanted[tid] else 'unticked'} {tid} in {info['tasks_md']}")
    if missing:
        print(f"note: no tasks.md line for {', '.join(missing)}", file=sys.stderr)


# ----------------------------------------------------------------------------- scheduling

def plan_next(board, parallel: int, strict_files: bool = False):
    idx = index_tasks(board)
    height, ndesc, _ = priorities(idx)
    inflight = [t for t in idx.values() if status_of(t) in INFLIGHT]
    locked = [(f, t["id"]) for t in inflight if kind_of(t) == "code" for f in files_of(t, strict_files)]
    slots = max(0, parallel - len(inflight))
    ready = sorted(
        (t for t in idx.values() if is_ready(t, idx)),
        key=lambda t: (-height[t["id"]], -ndesc[t["id"]], natural_key(t["id"])),
    )
    start, deferred = [], []
    for task in ready:
        if len(start) >= slots:
            break
        files = files_of(task, strict_files) if kind_of(task) == "code" else []
        clash = next(((f, owner) for f in files for (g, owner) in locked if paths_overlap(f, g)), None)
        if clash:
            deferred.append({"id": task["id"], "waits_for": clash[1], "path": clash[0]})
            continue
        start.append(task)
        locked.extend((f, task["id"]) for f in files)
    pending = [t for t in idx.values() if status_of(t) == "pending"]
    waiting = [t["id"] for t in pending if not is_ready(t, idx)]
    stopped = [t["id"] for t in idx.values() if status_of(t) in STOPPED]
    return {
        "start": [
            {
                "id": t["id"], "title": t.get("title", ""), "agent": agent_full(agent_of(t)),
                "kind": kind_of(t), "files": files_of(t), "critical_path": height[t["id"]],
                "unblocks": ndesc[t["id"]],
                "security_sensitive": bool(t.get("security_sensitive")),
            }
            for t in start
        ],
        "deferred": deferred,
        "in_flight": [t["id"] for t in inflight],
        "slots": slots,
        "parallel": parallel,
        "ready_total": len(ready),
        "waiting_on_deps": sorted(waiting, key=natural_key),
        "stopped": sorted(stopped, key=natural_key),
        "complete": not pending and not inflight,
        "stuck": not inflight and not ready and bool(pending),
    }


def simulate_waves(board, parallel: int, strict_files: bool = False):
    idx = index_tasks(board)
    height, ndesc, _ = priorities(idx)
    done = {k for k, t in idx.items() if status_of(t) in FINISHED}
    todo = {k for k, t in idx.items() if status_of(t) not in FINISHED | STOPPED}
    critical = max((height[k] for k in todo), default=0)
    waves = []
    while todo:
        ready = [k for k in todo if all(d in idx and d in done for d in deps_of(idx[k]))]
        if not ready:
            break
        ready.sort(key=lambda k: (0 if status_of(idx[k]) in INFLIGHT else 1,
                                  -height[k], -ndesc[k], natural_key(k)))
        wave, locked = [], []
        for key in ready:
            if len(wave) >= parallel:
                break
            files = files_of(idx[key], strict_files) if kind_of(idx[key]) == "code" else []
            if any(paths_overlap(f, g) for f in files for g in locked):
                continue
            wave.append(key)
            locked.extend(files)
        waves.append(wave)
        done.update(wave)
        todo.difference_update(wave)
    return waves, sorted(todo, key=natural_key), critical


# ----------------------------------------------------------------------------- commands

def cmd_latest(args) -> int:
    board = latest_board()
    if not board:
        die("no boards found under .bosun/plans/")
    print(board)
    return 0


def cmd_init(args) -> int:
    if not SLUG_RE.match(args.slug):
        die("slug must be lowercase letters, digits, . _ - (max 64 chars)")
    plan_dir = find_project_root() / ".bosun" / "plans" / args.slug
    path = plan_dir / "tasks.json"
    if path.exists() and not args.force:
        die(f"{path} already exists (use --force to overwrite)")
    plan_dir.mkdir(parents=True, exist_ok=True)
    board = {"name": args.slug, "title": args.title or args.slug, "version": 1,
             "meta": {"created_at": now_iso()}, "tasks": []}
    if args.openspec_change:
        board["meta"]["openspec_change"] = args.openspec_change
    save_board(path, board)
    print(path)
    return 0


def cmd_validate(args) -> int:
    path = resolve_board(args.board)
    board = load_board(path)
    errors, warnings = validate_board(board)
    if args.json:
        emit_json({"board": str(path), "ok": not errors, "errors": errors, "warnings": warnings,
                   "tasks": len(board.get("tasks", []))})
        return 1 if errors else 0
    for err in errors:
        print(f"ERROR   {err}")
    for warn in warnings:
        print(f"warning {warn}")
    total = len(board.get("tasks", []))
    print(f"{'INVALID' if errors else 'OK'}: {total} tasks, {len(errors)} errors, {len(warnings)} warnings ({path})")
    return 1 if errors else 0


def require_valid(board, path) -> None:
    errors, _ = validate_board(board)
    if errors:
        die(f"{path} is invalid; run `validate` first:\n  " + "\n  ".join(errors[:10]))


def cmd_next(args) -> int:
    path = resolve_board(args.board)
    board = load_board(path)
    require_valid(board, path)
    parallel = args.parallel or default_parallel(board, path)
    result = plan_next(board, parallel, args.strict_files)
    if args.json:
        emit_json(result)
        return 0
    print(f"in flight: {len(result['in_flight'])}/{parallel}"
          + (f" ({', '.join(result['in_flight'])})" if result["in_flight"] else "")
          + f"   free slots: {result['slots']}")
    if result["complete"]:
        print("board complete: nothing pending or in flight")
    if result["start"]:
        print("start now:")
        for t in result["start"]:
            flag = "  [security]" if t["security_sensitive"] else ""
            print(f"  {t['id']:<8} {t['agent']:<28} {t['title']}  "
                  f"(critical path {t['critical_path']}, unblocks {t['unblocks']}){flag}")
    elif not result["complete"]:
        print("nothing to start right now")
    for d in result["deferred"]:
        print(f"  deferred {d['id']}: waits for {d['waits_for']} ({d['path']})")
    if result["waiting_on_deps"]:
        print(f"waiting on deps: {len(result['waiting_on_deps'])} task(s)")
    if result["stopped"]:
        print(f"blocked/failed: {', '.join(result['stopped'])}")
    if result["stuck"]:
        print("STUCK: pending tasks remain but none can start; unblock or skip the blocked/failed tasks")
    return 0


def cmd_set(args) -> int:
    path = resolve_board(args.board)
    with board_lock(path):
        board = load_board(path)
        idx = index_tasks(board)
        missing = [i for i in args.ids if i not in idx]
        if missing:
            die(f"unknown task id(s): {', '.join(missing)}")
        stamp = now_iso()
        ticks = {}
        for tid in args.ids:
            task = idx[tid]
            old = status_of(task)
            if args.status and args.status != old:
                new = args.status
                if new != "skipped":
                    ticks[tid] = new == "done"
                task["status"] = new
                if new in INFLIGHT and old not in INFLIGHT:
                    task["attempts"] = int(task.get("attempts") or 0) + (1 if new == "in_progress" else 0)
                    task["started_at"] = stamp
                    task.pop("finished_at", None)
                if new in FINISHED | STOPPED:
                    task["finished_at"] = stamp
                if new == "pending":
                    task.pop("started_at", None)
                    task.pop("finished_at", None)
                history = task.setdefault("history", [])
                history.append({"ts": stamp, "from": old, "to": new, **({"note": args.note} if args.note else {})})
            for field in ("assignee", "branch", "worktree", "commit", "summary"):
                value = getattr(args, field)
                if value is not None:
                    if value == "":
                        task.pop(field, None)
                    else:
                        task[field] = value
            if args.note:
                task.setdefault("notes", []).append(f"{stamp} {args.note}")
        board.setdefault("meta", {})["updated_at"] = stamp
        save_board(path, board)
        tick_tasks_md(board, path, ticks)
    if args.status:
        print(f"{', '.join(args.ids)} -> {args.status}")
    else:
        print(f"updated {', '.join(args.ids)}")
    return 0


def split_csv(values):
    out = []
    for value in values or []:
        out.extend(v.strip() for v in value.split(",") if v.strip())
    return out


def cmd_add(args) -> int:
    path = resolve_board(args.board)
    with board_lock(path):
        board = load_board(path)
        idx = index_tasks(board)
        if args.id in idx:
            die(f"task {args.id} already exists")
        task = {"id": args.id, "title": args.title, "agent": args.agent, "deps": split_csv(args.deps),
                "files": split_csv(args.files), "acceptance": args.acceptance or [], "status": "pending"}
        if args.spec_ref:
            task["spec_refs"] = args.spec_ref
        change = openspec_change(board, path)
        if change and not OS_TASK_ID.fullmatch(args.id):
            die(f"{args.id}: tasks of an OpenSpec plan use tasks.md ids such as 7.1")
        if change and not change["tasks_md"].is_file():
            die(f"{change['tasks_md']} not found")
        for field in ("description", "kind", "size", "risk"):
            value = getattr(args, field)
            if value:
                task[field] = value
        if args.security_sensitive:
            task["security_sensitive"] = True
        candidate = dict(board)
        candidate["tasks"] = list(board["tasks"]) + [task]
        errors, warnings = validate_board(candidate)
        if errors:
            die("task rejected:\n  " + "\n  ".join(errors))
        board["tasks"].append(task)
        board.setdefault("meta", {})["updated_at"] = now_iso()
        save_board(path, board)
        if change and not any(t["id"] == args.id for t in parse_tasks_md(read_text(change["tasks_md"]) or "")):
            append_task_line(change["tasks_md"], args.id, args.title)
            print(f"added '- [ ] {args.id}' to {change['tasks_md']}")
    for warn in warnings:
        if warn.startswith(args.id) or f" {args.id} " in warn:
            print(f"warning {warn}")
    print(f"added {args.id}")
    return 0


def cmd_brief(args) -> int:
    path = resolve_board(args.board).resolve()
    board = load_board(path)
    idx = index_tasks(board)
    task = idx.get(args.id) or die(f"unknown task id {args.id}")
    plan_md = path.parent / "PLAN.md"
    info = openspec_change(board, path)
    lines = [f"# Task {task['id']}: {task.get('title', '')}", ""]
    lines.append(f"- Plan: {board.get('title') or board.get('name', '')}")
    if info:
        lines.append(f"- OpenSpec change (read-only for you): {info['dir']}/ "
                     "(proposal.md = why, design.md = how, specs/ = required behavior)")
    elif plan_md.is_file():
        lines.append(f"- PLAN.md (read the sections relevant to this task): {plan_md}")
    lines.append(f"- Board (read-only for you): {path}")
    lines.append(f"- Agent: {agent_full(agent_of(task))}   Kind: {kind_of(task)}   Size: {task.get('size', 'M')}"
                 f"   Risk: {task.get('risk', 'unknown')}"
                 + ("   SECURITY-SENSITIVE" if task.get("security_sensitive") else ""))
    attempts = int(task.get("attempts") or 0)
    if attempts > 1:
        lines.append(f"- Attempt: {attempts}")
    fallback = "(none; follow the title, the requirements below and design.md)" if info \
        else "(none; follow the title and PLAN.md)"
    lines += ["", "## Description", "", task.get("description") or fallback, ""]
    lines += ["## Acceptance criteria", ""]
    lines += [f"- [ ] {a}" for a in task.get("acceptance") or []] or ["- (none given; derive them from the plan and state them in your result)"]
    lines.append("")
    refs = spec_refs_of(task)
    if info and refs:
        reqs = spec_requirements(load_change(info))
        lines += ["## Requirements this task implements (verbatim from the change's specs)", "",
                  "Every scenario needs a test that fails without your change; name tests after scenarios "
                  "where the framework allows. A MODIFIED requirement replaces the old one in full.", ""]
        blocks, budget = [], BRIEF_SPEC_CHARS
        for ref in refs:
            req = reqs.get(ref)
            if req is None:
                blocks += [f"- {ref}: NOT FOUND in the change; ask the manager", ""]
                continue
            header = f"From {req['path']} ({req['section'].upper()}):"
            if len(req["raw"]) <= budget:
                blocks += [header, "", req["raw"], ""]
                budget -= len(req["raw"])
            else:
                blocks += [f"- {ref}: read it in {info['dir'] / req['path']} (line {req['line']})", ""]
        lines += blocks
    files = files_of(task)
    lines += ["## Files you own", ""]
    if files:
        lines += [f"- {f}" for f in files]
        lines += ["", "Anything else is owned by other tasks or shared. Change it only if unavoidable, "
                  "keep the edit minimal, and report it under out_of_scope_changes."]
    else:
        lines.append("- (not declared; keep the change as small as possible and list every file you touch)")
    lines.append("")
    deps = [idx[d] for d in deps_of(task) if d in idx]
    if deps:
        lines += ["## Completed dependencies (build on these; don't redo them)", ""]
        for dep in deps:
            extra = ", ".join(x for x in (
                f"commit {dep['commit']}" if dep.get("commit") else "",
                f"files: {', '.join(files_of(dep))}" if files_of(dep) else "",
            ) if x)
            lines.append(f"- {dep['id']} [{status_of(dep)}] {dep.get('title', '')}" + (f" ({extra})" if extra else ""))
            if dep.get("summary"):
                lines.append(f"  - result: {dep['summary']}")
        lines.append("")
    others = [t for t in idx.values() if status_of(t) in INFLIGHT and t["id"] != task["id"] and files_of(t)]
    if others:
        lines += ["## In flight right now (do not touch their files)", ""]
        lines += [f"- {t['id']} {t.get('title', '')}: {', '.join(files_of(t))}" for t in others]
        lines.append("")
    notes = task.get("notes") or []
    if notes:
        lines += ["## Notes from earlier attempts and reviews", ""]
        lines += [f"- {n}" for n in notes[-8:]]
        lines.append("")
    print("\n".join(lines).rstrip() + "\n")
    return 0


def cmd_spec_check(args) -> int:
    path = resolve_board(args.board)
    board = load_board(path)
    errors, warnings, report = spec_check(board, path)
    if args.json:
        emit_json(dict(report, ok=not errors, errors=errors, warnings=warnings))
        return 1 if errors else 0
    for err in errors:
        print(f"ERROR   {err}")
    for warn in warnings:
        print(f"warning {warn}")
    if report.get("requirements") is not None and "coverage" in report:
        md = report["tasks_md"]
        print(f"{'FAILED' if errors else 'OK'}: change {report['change']}: {report['requirements']} requirement(s), "
              f"{len(report['coverage'])} covered by tasks; tasks.md {md['ticked']}/{md['total']} ticked; "
              f"{len(errors)} errors, {len(warnings)} warnings")
    else:
        print(f"FAILED: {len(errors)} error(s)")
    return 1 if errors else 0


def cmd_sync(args) -> int:
    path = resolve_board(args.board)
    board = load_board(path)
    info = openspec_change(board, path)
    if info is None:
        die("board has no meta.openspec_change; nothing to sync")
    if not info["tasks_md"].is_file():
        die(f"{info['tasks_md']} not found")
    wanted = {t["id"]: status_of(t) == "done" for t in index_tasks(board).values() if status_of(t) != "skipped"}
    changed, missing = mark_tasks_md(info["tasks_md"], wanted, dry_run=args.dry_run)
    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {len(changed)} checkbox(es) in {info['tasks_md']}" + (f": {', '.join(changed)}" if changed else ""))
    if missing:
        print(f"no tasks.md line for: {', '.join(missing)} (run spec-check)")
    return 0


def progress_bar(fraction: float, width: int = 24) -> str:
    filled = int(round(fraction * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def cmd_status(args) -> int:
    path = resolve_board(args.board)
    board = load_board(path)
    idx = index_tasks(board)
    parallel = args.parallel or default_parallel(board, path)
    counts = {s: 0 for s in STATUSES}
    for task in idx.values():
        counts[status_of(task)] = counts.get(status_of(task), 0) + 1
    total = len(idx)
    finished = counts["done"] + counts["skipped"]
    errors, _ = validate_board(board)
    waves, unschedulable, critical = simulate_waves(board, parallel) if not errors else ([], [], 0)
    nxt = plan_next(board, parallel) if not errors else None
    inflight = sorted((t for t in idx.values() if status_of(t) in INFLIGHT), key=lambda t: natural_key(t["id"]))
    stopped = sorted((t for t in idx.values() if status_of(t) in STOPPED), key=lambda t: natural_key(t["id"]))
    recent = sorted((t for t in idx.values() if status_of(t) == "done" and t.get("finished_at")),
                    key=lambda t: t["finished_at"], reverse=True)[:5]
    meta = board.get("meta") or {}
    spec = None
    info = openspec_change(board, path)
    if info:
        live = info["dir"].is_dir()
        md_path = info["tasks_md"] if live else (info["archived"] / "tasks.md" if info["archived"] else None)
        md = parse_tasks_md((read_text(md_path) if md_path else None) or "")
        ticked = {t["id"] for t in md if t["done"] and t["id"]}
        spec = {"change": info["id"], "dir": str(info["dir"]), "exists": live,
                "archived": str(info["archived"]) if info["archived"] else None,
                "tasks_md_total": len(md), "tasks_md_ticked": sum(1 for t in md if t["done"]),
                "out_of_sync": sorted((k for k, t in idx.items() if live and status_of(t) != "skipped"
                                       and (k in ticked) != (status_of(t) == "done")), key=natural_key)}
    if args.json:
        emit_json({
            "board": str(path), "name": board.get("name"), "total": total, "counts": counts,
            "percent_done": round(100.0 * finished / total, 1) if total else 0.0,
            "in_flight": [{"id": t["id"], "status": status_of(t), "assignee": t.get("assignee"),
                           "since": t.get("started_at"), "elapsed": human_age(t.get("started_at")),
                           "attempts": t.get("attempts", 0), "title": t.get("title")} for t in inflight],
            "stopped": [{"id": t["id"], "status": status_of(t), "title": t.get("title"),
                         "last_note": (t.get("notes") or [None])[-1]} for t in stopped],
            "ready": [s["id"] for s in nxt["start"]] if nxt else [],
            "waves_left": len(waves), "critical_path_left": critical, "unschedulable": unschedulable,
            "stuck": bool(nxt and nxt["stuck"]), "complete": bool(nxt and nxt["complete"]),
            "meta": meta, "errors": errors, "openspec": spec,
        })
        return 0
    print(f"Plan: {board.get('title') or board.get('name')}  ({path})")
    if meta.get("work_branch"):
        print(f"Branch: {meta.get('work_branch')} (base {meta.get('base_branch', '?')}"
              + (f" @ {str(meta['base_commit'])[:10]}" if meta.get("base_commit") else "") + ")")
    if spec:
        state = "" if spec["exists"] else (f" (archived: {spec['archived']})" if spec["archived"]
                                            else " (change directory missing)")
        print(f"OpenSpec: change {spec['change']}{state}"
              + f"; tasks.md {spec['tasks_md_ticked']}/{spec['tasks_md_total']} ticked"
              + (f"; out of sync: {', '.join(spec['out_of_sync'])} (run `sync`)" if spec["out_of_sync"] else ""))
    fraction = finished / total if total else 0.0
    print(f"Progress: {progress_bar(fraction)} {finished}/{total} finished ({fraction * 100:.0f}%)  "
          + "  ".join(f"{s}: {counts[s]}" for s in STATUSES if counts[s] and s not in FINISHED))
    if errors:
        print(f"Board has {len(errors)} validation error(s); run `validate`.")
    else:
        print(f"Remaining: ~{len(waves)} wave(s) at parallel {parallel}; critical path {critical} size-units"
              + (f"; unschedulable: {', '.join(unschedulable)}" if unschedulable else ""))
    if inflight:
        print("\nIn flight:")
        for t in inflight:
            print(f"  {t['id']:<8} {status_of(t):<12} {str(t.get('assignee') or '-'):<26} "
                  f"{human_age(t.get('started_at')):>7}  try {t.get('attempts', 1)}  {t.get('title', '')}")
    if stopped:
        print("\nBlocked / failed:")
        for t in stopped:
            note = (t.get("notes") or [""])[-1]
            print(f"  {t['id']:<8} {status_of(t):<8} {t.get('title', '')}" + (f"\n           last note: {note}" if note else ""))
    if nxt and nxt["start"]:
        print("\nReady next: " + ", ".join(s["id"] for s in nxt["start"]))
    if nxt and nxt["stuck"]:
        print("STUCK: nothing can start; resolve the blocked/failed tasks above")
    if recent:
        print("\nRecently done: " + ", ".join(f"{t['id']} ({human_age(t['finished_at'])} ago)" for t in recent))
    return 0


def cmd_waves(args) -> int:
    path = resolve_board(args.board)
    board = load_board(path)
    require_valid(board, path)
    idx = index_tasks(board)
    parallel = args.parallel or default_parallel(board, path)
    waves, unschedulable, critical = simulate_waves(board, parallel, args.strict_files)
    if args.json:
        emit_json({"parallel": parallel, "waves": waves, "unschedulable": unschedulable,
                   "critical_path": critical, "max_width": max((len(w) for w in waves), default=0)})
        return 0
    remaining = sum(len(w) for w in waves)
    print(f"{remaining} task(s) in {len(waves)} wave(s) at parallel {parallel}; "
          f"widest wave {max((len(w) for w in waves), default=0)}; critical path {critical} size-units")
    for number, wave in enumerate(waves, 1):
        print(f"  wave {number:>2}: " + " | ".join(f"{k} {shorten(idx[k].get('title', ''), 38)}" for k in wave))
    if unschedulable:
        print("unschedulable (depend on blocked/failed tasks): " + ", ".join(unschedulable))
    return 0


def cmd_graph(args) -> int:
    path = resolve_board(args.board)
    board = load_board(path)
    idx = index_tasks(board)
    out = ["flowchart TD"]
    for key in sorted(idx, key=natural_key):
        task = idx[key]
        label = f"{key} · {task.get('title', '')}".replace('"', "'")
        out.append(f'  {safe_node(key)}["{label}"]:::{status_of(task)}')
    for key in sorted(idx, key=natural_key):
        for dep in deps_of(idx[key]):
            if dep in idx:
                out.append(f"  {safe_node(dep)} --> {safe_node(key)}")
    out += [
        "  classDef pending fill:#f3f4f6,stroke:#9ca3af,color:#111827",
        "  classDef in_progress fill:#dbeafe,stroke:#2563eb,color:#111827",
        "  classDef review fill:#ede9fe,stroke:#7c3aed,color:#111827",
        "  classDef done fill:#d1fae5,stroke:#059669,color:#111827",
        "  classDef blocked fill:#fef3c7,stroke:#d97706,color:#111827",
        "  classDef failed fill:#fee2e2,stroke:#dc2626,color:#111827",
        "  classDef skipped fill:#f3f4f6,stroke:#d1d5db,color:#6b7280",
    ]
    print("\n".join(out))
    return 0


def safe_node(key: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", key)


def cmd_meta(args) -> int:
    path = resolve_board(args.board)
    if not args.set:
        emit_json(load_board(path).get("meta") or {})
        return 0
    with board_lock(path):
        board = load_board(path)
        meta = board.setdefault("meta", {})
        for item in args.set:
            if "=" not in item:
                die(f"--set expects key=value, got {item!r}")
            key, value = item.split("=", 1)
            key = key.strip()
            if value == "":
                meta.pop(key, None)
            elif value.isdigit():
                meta[key] = int(value)
            else:
                meta[key] = value
        meta["updated_at"] = now_iso()
        save_board(path, board)
    emit_json(board["meta"])
    return 0


def cmd_activity(args) -> int:
    path = resolve_board(args.board)
    log_path = bosun_dir_for(path) / "activity.jsonl"
    events = []
    if log_path.is_file():
        with open(log_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                with contextlib.suppress(json.JSONDecodeError):
                    event = json.loads(line)
                    if isinstance(event, dict):
                        events.append(event)
    running = {}
    for event in events:
        agent_id = event.get("agent_id")
        if event.get("event") == "start" and agent_id:
            running[agent_id] = event
        elif event.get("event") == "stop" and agent_id:
            running.pop(agent_id, None)
    tail = events[-args.tail:] if args.tail > 0 else events
    if args.json:
        emit_json({"log": str(log_path), "running": list(running.values()), "events": tail})
        return 0
    if not events:
        print(f"no activity recorded yet ({log_path})")
        return 0
    print(f"Agents running (per hook log): {len(running)}")
    for event in running.values():
        print(f"  {event.get('agent_type', '?'):<28} id={event.get('agent_id', '?')}  for {human_age(event.get('ts'))}")
    print(f"\nLast {len(tail)} event(s):")
    for event in tail:
        bits = [str(event.get("ts", "?")), f"{event.get('event', '?'):<5}", str(event.get("agent_type", "?"))]
        for key in ("task", "status"):
            if event.get(key):
                bits.append(f"{key}={event[key]}")
        if event.get("summary"):
            bits.append(f"- {event['summary']}")
        print("  " + "  ".join(bits))
    return 0


def cmd_schema(args) -> int:
    print(SCHEMA_DOC)
    return 0


def cmd_example(args) -> int:
    emit_json(EXAMPLE_BOARD)
    return 0


# ----------------------------------------------------------------------------- cli

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="taskboard.py",
        description="bosun task board: dependency-aware, file-ownership-aware scheduling for parallel agents.",
    )
    parser.add_argument("--version", action="version", version=f"bosun taskboard {VERSION}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    def board_cmd(name, help_text, func):
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.add_argument("board", help="tasks.json path, plan directory, or plan slug")
        p.set_defaults(func=func)
        return p

    p = sub.add_parser("latest", help="print the most recently modified board under .bosun/plans/")
    p.set_defaults(func=cmd_latest)

    p = sub.add_parser("init", help="create .bosun/plans/<slug>/tasks.json with no tasks")
    p.add_argument("slug")
    p.add_argument("--title")
    p.add_argument("--openspec-change", metavar="ID", help="link the board to openspec/changes/<ID>/")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = board_cmd("validate", "check schema, ids, dependencies, cycles and file-ownership overlaps", cmd_validate)
    p.add_argument("--json", action="store_true")

    p = board_cmd("next", "tasks to start now: deps finished, files disjoint from in-flight work, critical path first", cmd_next)
    p.add_argument("--parallel", type=int, help="max tasks in flight (default: meta.max_parallel, config, or 4)")
    p.add_argument("--strict-files", action="store_true", help="code tasks with no declared files run alone")
    p.add_argument("--json", action="store_true")

    p = board_cmd("set", "update one or more tasks (status, assignee, branch, worktree, commit, summary, note)", cmd_set)
    p.add_argument("ids", nargs="+", metavar="ID")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--assignee")
    p.add_argument("--branch")
    p.add_argument("--worktree")
    p.add_argument("--commit")
    p.add_argument("--summary")
    p.add_argument("--note")

    p = board_cmd("add", "append a task (validated: no unknown deps, no cycles, unique id)", cmd_add)
    p.add_argument("--id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--agent", default="implementer")
    p.add_argument("--kind", choices=("code", "report"))
    p.add_argument("--deps", action="append", help="comma-separated ids (repeatable)")
    p.add_argument("--files", action="append", help="comma-separated paths (repeatable)")
    p.add_argument("--acceptance", action="append", help="one criterion (repeatable)")
    p.add_argument("--description")
    p.add_argument("--size", choices=("S", "M", "L"))
    p.add_argument("--risk", choices=("low", "medium", "high"))
    p.add_argument("--security-sensitive", action="store_true")
    p.add_argument("--spec-ref", action="append", metavar="CAPABILITY#REQUIREMENT",
                   help="requirement this task implements (repeatable; OpenSpec plans)")

    p = board_cmd("brief", "print a self-contained task brief to paste into an agent prompt", cmd_brief)
    p.add_argument("id")

    p = board_cmd("status", "progress dashboard", cmd_status)
    p.add_argument("--parallel", type=int)
    p.add_argument("--json", action="store_true")

    p = board_cmd("waves", "estimate the remaining schedule as parallel waves", cmd_waves)
    p.add_argument("--parallel", type=int)
    p.add_argument("--strict-files", action="store_true")
    p.add_argument("--json", action="store_true")

    board_cmd("graph", "print the dependency graph as a Mermaid flowchart", cmd_graph)

    p = board_cmd("spec-check", "OpenSpec plans: check the change's specs, requirement coverage and tasks.md "
                  "against the board", cmd_spec_check)
    p.add_argument("--json", action="store_true")

    p = board_cmd("sync", "OpenSpec plans: tick tasks.md for done tasks and untick the rest (skipped untouched)",
                  cmd_sync)
    p.add_argument("--dry-run", action="store_true")

    p = board_cmd("meta", "show board meta, or set keys with --set key=value (empty value deletes)", cmd_meta)
    p.add_argument("--set", action="append", metavar="KEY=VALUE")

    p = board_cmd("activity", "agent start/stop events recorded by the bosun hooks", cmd_activity)
    p.add_argument("--tail", type=int, default=15)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("schema", help="print the annotated board schema and planning rules")
    p.set_defaults(func=cmd_schema)
    p = sub.add_parser("example", help="print a small example board")
    p.set_defaults(func=cmd_example)
    return parser


def main(argv=None) -> int:
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # `taskboard.py status | head` exits quietly
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
