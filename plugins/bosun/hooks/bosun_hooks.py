#!/usr/bin/env python3
"""bosun hooks: safety guard, activity log and context injection for bosun subagents.

Wired up in hooks/hooks.json for these events:
  PreToolUse (Bash, Edit, Write, NotebookEdit)  guard: deny risky actions by bosun subagents
  SubagentStart (bosun:*)                     log the start; inject the project profile and output style
  SubagentStop  (bosun:*)                     log the BOSUN-RESULT status

Scope: only tool calls made inside a bosun subagent (agent_type "bosun:...") are checked.
Your main session and every other agent pass through untouched.

Environment switches:
  BOSUN_GUARD=0            turn the guard off
  BOSUN_ENFORCE_RESULT=1   make a bosun subagent continue once if it stops without a result block
  BOSUN_OUTPUT_STYLE=...   override output_style from .bosun/config.json for this session

The script fails open: if anything goes wrong internally it exits 0, so a bug here can never
block your session. Standard library only; Python 3.10+ (tested in CI on 3.10 and 3.13).
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
import time

CREW_PREFIX = "bosun:"
RESULT_MARKER = "BOSUN-RESULT"
MAX_CONTEXT_CHARS = 4000
DANGEROUS_PATHSPECS = {".", "./", ":/", "*", ":(top)", "-A"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
INTERPRETERS = SHELLS | {"python", "python3", "node", "perl", "ruby", "php", "pwsh", "powershell"}
WRAPPERS = {"command", "builtin", "nice", "nohup", "time", "stdbuf", "env", "exec", "noglob",
            "xargs", "npx", "pnpx", "bunx", "uvx"}
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--exec-path"}

GH_WRITES = {
    "pr": {"create", "merge", "close", "reopen", "comment", "review", "edit", "ready", "lock", "unlock",
           "update-branch", "revert"},
    "issue": {"create", "close", "reopen", "comment", "edit", "delete", "transfer", "pin", "unpin", "lock",
              "unlock", "develop"},
    "release": {"create", "delete", "edit", "upload", "delete-asset"},
    "repo": {"create", "delete", "edit", "fork", "rename", "archive", "unarchive", "sync", "deploy-key",
             "set-default", "autolink"},
    "workflow": {"run", "enable", "disable"},
    "run": {"rerun", "cancel", "delete"},
    "secret": {"set", "delete", "remove"},
    "variable": {"set", "delete"},
    "label": {"create", "edit", "delete", "clone"},
    "gist": {"create", "edit", "delete", "rename"},
    "auth": {"login", "logout", "refresh", "setup-git", "switch", "token"},
    "ssh-key": {"add", "delete"},
    "gpg-key": {"add", "delete"},
    "cache": {"delete"},
    "codespace": {"create", "delete", "edit", "stop", "rebuild"},
    "project": {"create", "delete", "edit", "close", "copy", "link", "unlink", "item-add", "item-archive",
                "item-create", "item-delete", "item-edit", "field-create", "field-delete", "mark-template"},
    "extension": {"install", "remove", "upgrade"},
}
PUBLISH = {
    "npm": {"publish", "unpublish", "deprecate", "dist-tag", "owner", "access", "token", "adduser", "login"},
    "pnpm": {"publish"},
    "bun": {"publish"},
    "cargo": {"publish", "yank", "owner", "login"},
    "twine": {"upload", "register"},
    "poetry": {"publish"},
    "hatch": {"publish"},
    "flit": {"publish"},
    "uv": {"publish"},
    "gem": {"push", "yank", "owner", "signin"},
    "docker": {"push", "login"},
    "podman": {"push", "login"},
    "netlify": {"deploy"},
    "fly": {"deploy", "destroy", "scale", "secrets", "launch"},
    "flyctl": {"deploy", "destroy", "scale", "secrets", "launch"},
    "wrangler": {"deploy", "publish", "delete", "secret", "rollback"},
    "firebase": {"deploy"},
    "serverless": {"deploy", "remove"},
    "sls": {"deploy", "remove"},
    "cdk": {"deploy", "destroy"},
    "sam": {"deploy", "delete"},
}
INFRA = {
    "terraform": {"apply", "destroy", "import", "taint", "untaint", "state", "force-unlock"},
    "tofu": {"apply", "destroy", "import", "taint", "untaint", "state", "force-unlock"},
    "kubectl": {"apply", "create", "delete", "replace", "patch", "scale", "rollout", "edit", "drain", "cordon",
                "uncordon", "taint", "label", "annotate", "set", "expose", "run", "autoscale"},
    "helm": {"install", "upgrade", "uninstall", "delete", "rollback"},
    "pulumi": {"up", "update", "destroy", "import", "cancel", "state"},
}
RELEASE_SCRIPT = re.compile(r"^(deploy|publish|release)([:._-]|$)")
OPENSPEC_ENTRIES = ("changes/", "specs/", "config.yaml", "project.md", "AGENTS.md")

# Terse "caveman" output for agent reports: fewer output tokens for the manager to read.
STYLE_LEVELS = {
    "caveman-lite": "Prose: no filler, pleasantries or hedging words. Short, complete sentences.",
    "caveman": "Prose: terse fragments. Drop articles, filler, pleasantries and hedging words. "
               "Short words. One point per line.",
    "caveman-ultra": "Prose: telegraphic fragments. Abbreviate common words (cfg, fn, impl, deps, req, err). "
                     "Use -> for sequence and next step, never for cause.",
}
STYLE_RULES = (
    "Keep exact: code, commands, paths, identifiers, error text, numbers, versions, and text quoted from specs, "
    "tests or hypotheses.",
    "Keep the words that carry logic, even when dropping hedges: because, so, but, not, only, can, may, must.",
    "Write normally: code comments, commit messages, PR text, docs, OpenSpec files, user-facing strings.",
    "Use plain full sentences for security warnings, destructive or irreversible steps, ordered instructions, "
    "questions, requests to confirm or decide, and statements of uncertainty.",
    "Never drop a fact to save words: keep every failure and every uncertainty label "
    "(unverified, not run, assumption).",
)


# ----------------------------------------------------------------------------- shell parsing

def _matching(text: str, start: int, opener: str, closer: str) -> int:
    """Index of the closer matching text[start] == opener (quote-aware enough for guard purposes)."""
    depth, i = 0, start
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "'":
            end = text.find("'", i + 1)
            i = (end if end >= 0 else len(text)) + 1
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("unbalanced " + opener)


def tokenize(cmd: str):
    """Split a shell command into word/op/redir tokens. Returns (tokens, nested_command_strings)."""
    tokens, nested = [], []
    word, in_word = [], False
    heredocs = []
    i, n = 0, len(cmd)

    def flush():
        nonlocal word, in_word
        if in_word:
            tokens.append(("word", "".join(word)))
        word, in_word = [], False

    while i < n:
        ch = cmd[i]
        if ch == "\\":
            if i + 1 < n and cmd[i + 1] == "\n":
                i += 2
                continue
            if i + 1 < n:
                word.append(cmd[i + 1])
                in_word = True
            i += 2
            continue
        if ch == "'":
            end = cmd.find("'", i + 1)
            if end < 0:
                raise ValueError("unbalanced '")
            word.append(cmd[i + 1:end])
            in_word = True
            i = end + 1
            continue
        if ch == '"':
            j, buf = i + 1, []
            while j < n and cmd[j] != '"':
                if cmd[j] == "\\" and j + 1 < n and cmd[j + 1] in '"\\$`\n':
                    buf.append(cmd[j + 1])
                    j += 2
                    continue
                if cmd[j] == "$" and cmd[j + 1:j + 2] == "(":
                    end = _matching(cmd, j + 1, "(", ")")
                    nested.append(cmd[j + 2:end])
                    buf.append(cmd[j:end + 1])
                    j = end + 1
                    continue
                if cmd[j] == "`":
                    end = cmd.find("`", j + 1)
                    if end < 0:
                        raise ValueError("unbalanced `")
                    nested.append(cmd[j + 1:end])
                    j = end + 1
                    continue
                buf.append(cmd[j])
                j += 1
            if j >= n:
                raise ValueError('unbalanced "')
            word.append("".join(buf))
            in_word = True
            i = j + 1
            continue
        if ch == "$" and cmd[i + 1:i + 2] == "(":
            end = _matching(cmd, i + 1, "(", ")")
            nested.append(cmd[i + 2:end])
            word.append(cmd[i:end + 1])
            in_word = True
            i = end + 1
            continue
        if ch == "`":
            end = cmd.find("`", i + 1)
            if end < 0:
                raise ValueError("unbalanced `")
            nested.append(cmd[i + 1:end])
            i = end + 1
            continue
        if ch == "#" and not in_word:
            end = cmd.find("\n", i)
            i = n if end < 0 else end
            continue
        if ch in " \t\r":
            flush()
            i += 1
            continue
        if ch == "\n":
            flush()
            tokens.append(("op", "\n"))
            i += 1
            for delim in heredocs:  # skip heredoc bodies
                while i < n:
                    end = cmd.find("\n", i)
                    line = cmd[i:] if end < 0 else cmd[i:end]
                    i = n if end < 0 else end + 1
                    if line.strip() == delim:
                        break
            heredocs = []
            continue
        if cmd.startswith("&>", i) or ch in "<>":
            if in_word and "".join(word).isdigit():
                word, in_word = [], False  # file-descriptor number, e.g. 2>
            else:
                flush()
            j = i
            while j < n and cmd[j] in "<>&|-":
                j += 1
            op = cmd[i:j]
            tokens.append(("redir", op))
            i = j
            if op.startswith("<<") and not op.startswith("<<<"):
                k = i
                while k < n and cmd[k] in " \t":
                    k += 1
                m = re.match(r"""['"]?([A-Za-z0-9_]+)['"]?""", cmd[k:])
                if m:
                    heredocs.append(m.group(1))
            continue
        if ch in ";&|":
            flush()
            for op in ("&&", "||", "|&", ";;", "|", "&", ";"):
                if cmd.startswith(op, i):
                    tokens.append(("op", op))
                    i += len(op)
                    break
            continue
        if ch in "(){}" and not in_word:
            flush()
            tokens.append(("op", ch))
            i += 1
            continue
        word.append(ch)
        in_word = True
        i += 1
    flush()
    return tokens, nested


def split_commands(cmd: str):
    """Return (commands, pipes, nested): argv lists, (i, j) pipe links, and nested command strings."""
    tokens, nested = tokenize(cmd)
    commands, current, pipes = [], [], []
    skip_target, pipe_pending = False, False
    for kind, value in tokens:
        if kind == "redir":
            skip_target = True
            continue
        if kind == "word":
            if skip_target:
                skip_target = False
                continue
            current.append(value)
            continue
        skip_target = False
        if current:
            commands.append(current)
            if pipe_pending:
                pipes.append((len(commands) - 2, len(commands) - 1))
                pipe_pending = False
            current = []
        if value in ("|", "|&") and commands:
            pipe_pending = True
        elif value not in ("|", "|&"):
            pipe_pending = False
    if current:
        commands.append(current)
        if pipe_pending:
            pipes.append((len(commands) - 2, len(commands) - 1))
    return commands, pipes, nested


def strip_wrappers(argv):
    i = 0
    while i < len(argv):
        arg = argv[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", arg):
            i += 1
            continue
        base = os.path.basename(arg)
        if base in WRAPPERS:
            i += 1
            while i < len(argv) and argv[i].startswith("-"):
                i += 2 if (base == "nice" and argv[i] == "-n") or (base == "env" and argv[i] in ("-u", "-C")) else 1
            continue
        if base == "timeout":
            i += 1
            while i < len(argv) and argv[i].startswith("-"):
                i += 2 if argv[i] in ("-s", "-k", "--signal", "--kill-after") else 1
            i += 1  # the duration
            continue
        if base in ("pnpm", "npm", "yarn") and i + 1 < len(argv) and argv[i + 1] in ("exec", "dlx"):
            i += 2
            continue
        if base == "pipx" and i + 1 < len(argv) and argv[i + 1] == "run":
            i += 2
            continue
        break
    return argv[i:]


# ----------------------------------------------------------------------------- rules

def _short_flags(args):
    return "".join(a[1:] for a in args if re.match(r"^-[A-Za-z]+$", a))


def _has(args, *names):
    return any(a == n or (n.startswith("--") and a.startswith(n + "=")) for a in args for n in names)


def git_subcommand(args):
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in GIT_OPTS_WITH_VALUE:
            i += 2
            continue
        if arg.startswith("-"):
            i += 1
            continue
        return arg, args[i + 1:]
    return None, []


def check_git(args, isolated: bool):
    sub, rest = git_subcommand(args)
    if sub is None:
        return None
    short = _short_flags(rest)
    positional = [a for a in rest if not a.startswith("-")]
    if sub == "push":
        return "pushing is the user's call; the manager or /bosun:ship pushes. Report back instead."
    if sub == "pull":
        return "don't pull remote changes in the middle of a task; report back to the manager instead."
    if sub == "stash" and (not positional or positional[0] not in ("list", "show")):
        return "git stash is shared by every worktree and agent in this repo. Commit to your own branch, or report back."
    if sub == "worktree" and positional and positional[0] != "list":
        return "creating or removing worktrees is the manager's job."
    if sub in ("filter-branch", "filter-repo", "update-ref", "replace"):
        return f"git {sub} rewrites refs or history; ask the user."
    if sub == "reflog" and positional and positional[0] in ("expire", "delete"):
        return "expiring the reflog destroys recovery points; ask the user."
    if sub == "gc" and any(a.startswith("--prune") for a in rest):
        return "pruning objects destroys recovery points; ask the user."
    if sub == "branch" and (_has(rest, "--delete", "--move", "--force", "--set-upstream-to", "--unset-upstream")
                            or set(short) & set("dDmMfu")):
        return "deleting, renaming or force-moving branches is the manager's job."
    if sub == "tag" and (positional or _has(rest, "--delete") or set(short) & set("dasfm")) \
            and not (_has(rest, "--list") or "l" in short):
        return "creating or deleting tags is the user's call."
    if sub == "remote" and positional and positional[0] in (
            "add", "remove", "rm", "rename", "set-url", "set-head", "set-branches", "prune"):
        return "changing remotes affects the whole repository; ask the user."
    if sub == "config":
        reading = _has(rest, "--get", "--get-all", "--get-regexp", "--list", "--show-origin") or "l" in short
        if _has(rest, "--global", "--system", "--unset", "--unset-all", "--add", "--replace-all", "--edit",
                "--rename-section", "--remove-section") or "e" in short \
                or (positional and positional[0] in ("set", "unset", "edit", "rename-section", "remove-section")) \
                or (len(positional) >= 2 and not reading):
            return "changing git config affects the main repository; ask the user."
    if sub == "commit" and (_has(rest, "--no-verify") or "n" in short):
        return "--no-verify skips the project's hooks. Fix what the hook reports, or report the failure."
    if isolated:
        return None
    # Shared main checkout: other agents' uncommitted work lives here too.
    if sub == "submodule" and positional and positional[0] in ("update", "deinit", "add", "sync", "foreach"):
        return "changing submodule checkouts in the shared main checkout affects every agent; report back instead."
    if sub in ("commit", "merge", "rebase", "cherry-pick", "revert", "am", "switch", "reset", "add", "rm", "mv",
               "bisect"):
        return (f"`git {sub}` in the shared main checkout can capture or destroy other agents' work. "
                "In shared mode you don't stage or commit; the manager commits per task. Report back instead.")
    if sub == "checkout":
        if "--" in rest:
            paths = rest[rest.index("--") + 1:]
            if paths and not any(p in DANGEROUS_PATHSPECS for p in paths):
                return None
            return "discarding changes across the shared checkout would wipe other agents' work."
        return ("`git checkout` here can switch the manager's branch or discard other agents' work. "
                "To restore one of your own files use `git checkout -- <file>`.")
    if sub == "restore":
        if any(p in DANGEROUS_PATHSPECS for p in positional) or _has(rest, "--source") or "s" in short:
            return "repo-wide or source-based restore in the shared checkout would wipe other agents' work."
        return None
    if sub == "clean" and (_has(rest, "--force") or "f" in short):
        return "git clean deletes untracked files of every agent working in the shared checkout."
    return None


def check_rm(args):
    recursive = _has(args, "--recursive") or bool(set(_short_flags(args)) & set("rR"))
    if not recursive:
        return None
    for target in (a for a in args if not a.startswith("-")):
        t = target.replace("\\", "/")
        bare = t.rstrip("/") or "/"
        if bare in ("/", "/*", ".", "./*", "*", "..", ".git", ".bosun", ".claude") \
                or re.match(r"^/[^/]*$", bare) \
                or bare.startswith(("~", "$HOME", "${HOME}", "../")) \
                or bare.endswith(("/.git", "/..")) or "/.git/" in t:
            return f"refusing recursive delete of {target!r}; ask the user if this is really needed."
    return None


def check_gh(args):
    positional = [a for a in args if not a.startswith("-")]
    if not positional:
        return None
    group = positional[0]
    action = positional[1] if len(positional) > 1 else ""
    if group in GH_WRITES and action in GH_WRITES[group]:
        return f"`gh {group} {action}` acts on GitHub on the user's behalf; only the main session does that, after the user confirms."
    if group == "api":
        method = None
        for i, arg in enumerate(args):
            if arg in ("-X", "--method") and i + 1 < len(args):
                method = args[i + 1].upper()
            elif arg.startswith("--method="):
                method = arg.split("=", 1)[1].upper()
            elif re.match(r"^-X[A-Za-z]+$", arg):
                method = arg[2:].upper()
        has_body = any(a in ("-f", "-F", "--field", "--raw-field", "--input") or
                       a.startswith(("--field=", "--raw-field=", "--input=")) for a in args)
        endpoint = action
        if endpoint == "graphql":
            if any("mutation" in a for a in args):
                return "GraphQL mutations act on GitHub on the user's behalf; ask the user."
            return None
        if method in ("POST", "PUT", "PATCH", "DELETE") or (method is None and has_body):
            return "write requests to the GitHub API act on the user's behalf; ask the user."
    return None


def check_argv(argv, isolated: bool):
    if not argv:
        return None
    if os.path.basename(argv[0]) in ("sudo", "doas", "su"):
        return "privilege escalation (sudo) needs the user."
    argv = strip_wrappers(argv)
    if not argv:
        return None
    prog = os.path.basename(argv[0])
    args = argv[1:]
    positional = [a for a in args if not a.startswith("-")]
    if prog in ("sudo", "doas", "su"):
        return "privilege escalation (sudo) needs the user."
    if prog in SHELLS:
        for i, arg in enumerate(args):
            if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", arg) and i + 1 < len(args):
                return check_command(args[i + 1], isolated)
        return None
    if prog == "eval":
        return check_command(" ".join(args), isolated)
    if prog == "git":
        return check_git(args, isolated)
    if prog == "rm":
        return check_rm(args)
    if prog == "gh":
        return check_gh(args)
    if prog in PUBLISH and positional and positional[0] in PUBLISH[prog]:
        return f"`{prog} {positional[0]}` publishes or deploys outside this machine; that is the user's call."
    if prog == "yarn" and positional[:2] == ["npm", "publish"]:
        return "publishing packages is the user's call."
    if prog == "dotnet" and positional[:2] == ["nuget", "push"]:
        return "publishing packages is the user's call."
    if prog in ("mvn", "mvnw", "./mvnw") and any(p in ("deploy", "release:perform") for p in positional):
        return "publishing artifacts is the user's call."
    if prog in ("gradle", "gradlew") and any(p.startswith("publish") for p in positional):
        return "publishing artifacts is the user's call."
    if prog == "vercel" and (not positional or positional[0] in ("deploy", "promote", "rollback", "remove", "rm", "alias")
                             or "--prod" in args):
        return "deploying is the user's call."
    if prog in INFRA and positional and positional[0] in INFRA[prog]:
        return f"`{prog} {positional[0]}` changes real infrastructure; ask the user."
    if prog == "ansible-playbook":
        return "running playbooks changes real machines; ask the user."
    if prog in ("docker", "podman"):
        if len(positional) >= 2 and positional[0] in ("system", "volume", "image", "container", "network", "builder") \
                and positional[1] in ("prune", "rm"):
            return "pruning or removing Docker resources can delete the user's data; ask the user."
        if positional[:2] == ["compose", "down"] and (_has(args, "--volumes") or "v" in _short_flags(args)):
            return "`compose down -v` deletes volumes (data); ask the user."
    if prog in ("npm", "pnpm", "yarn", "bun"):
        script = None
        if positional and positional[0] in ("run", "run-script") and len(positional) > 1:
            script = positional[1]
        elif prog in ("yarn", "pnpm", "bun") and positional and positional[0] not in ("run", "install", "add"):
            script = positional[0]
        if script and RELEASE_SCRIPT.match(script):
            return f"the `{script}` script looks like a release or deploy; that is the user's call."
    if prog == "make" and any(RELEASE_SCRIPT.match(p) for p in positional):
        return "that make target looks like a release or deploy; that is the user's call."
    return None


def check_command(cmd: str, isolated: bool, depth: int = 0):
    if depth > 4 or not cmd.strip():
        return None
    try:
        commands, pipes, nested = split_commands(cmd)
    except ValueError:
        # Unparseable: fall back to a conservative scan for the worst patterns only.
        if re.search(r"(^|[;&|\s])git\s+(-\S+\s+)*push\b", cmd):
            return "pushing is the user's call; report back instead."
        return None
    for src, dst in pipes:
        left = strip_wrappers(commands[src])
        right = strip_wrappers(commands[dst])
        if left and right and os.path.basename(left[0]) in ("curl", "wget") \
                and os.path.basename(right[0]) in INTERPRETERS | {"sudo"}:
            return "piping a download into a shell runs unreviewed code; download, inspect, then run it, or ask the user."
    for argv in commands:
        reason = check_argv(argv, isolated)
        if reason:
            return reason
    for inner in nested:
        reason = check_command(inner, isolated, depth + 1)
        if reason:
            return reason
    return None


# ----------------------------------------------------------------------------- paths & project

def normalize(path: str) -> str:
    return str(path or "").replace("\\", "/")


def strip_dot_slash(path: str) -> str:
    while path.startswith("./"):
        path = path[2:]
    return path


def is_isolated(cwd: str) -> bool:
    """True when cwd is inside a linked git worktree (its .git is a file, not a directory)."""
    cwd = normalize(cwd)
    if "/.claude/worktrees/" in cwd + "/":
        return True
    path = cwd
    for _ in range(40):
        if not path:
            break
        git = os.path.join(path, ".git")
        if os.path.isfile(git):
            return True
        if os.path.isdir(git):
            return False
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return False


def project_dir(data):
    for candidate in (os.environ.get("CLAUDE_PROJECT_DIR"), data.get("cwd")):
        if not candidate:
            continue
        candidate = normalize(candidate)
        if "/.claude/worktrees/" in candidate:
            candidate = candidate.split("/.claude/worktrees/")[0]
        if os.path.isdir(os.path.join(candidate, ".bosun")):
            return candidate
    return None


def load_config(root):
    if not root:
        return {}
    try:
        with open(os.path.join(root, ".bosun", "config.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def relative_to_repo(file_path: str, data):
    path = normalize(file_path)
    marker = "/.claude/worktrees/"
    if marker in path:
        rest = path.split(marker, 1)[1]
        return rest.split("/", 1)[1] if "/" in rest else ""
    for root in (os.environ.get("CLAUDE_PROJECT_DIR"), data.get("cwd")):
        root = normalize(root).rstrip("/")
        if root and (path == root or path.startswith(root + "/")):
            return path[len(root):].lstrip("/")
    if not path.startswith("/") and not re.match(r"^[A-Za-z]:/", path):
        return strip_dot_slash(path)
    return None


def matches(rel: str, pattern: str) -> bool:
    pattern = strip_dot_slash(normalize(pattern))
    if pattern.endswith("/"):
        return rel.startswith(pattern)
    if pattern.endswith("/**") and rel.startswith(pattern[:-2]):
        return True
    return fnmatch.fnmatch(rel, pattern)


def check_path(file_path: str, data, agent: str):
    rel = relative_to_repo(file_path, data)
    if rel is None:
        return None  # outside the repository (e.g. a temp dir)
    if rel == ".git" or rel.startswith(".git/"):
        return "editing git internals is not allowed."
    if rel in (".claude/settings.json", ".claude/settings.local.json"):
        return "agents must not change Claude Code settings or permissions; ask the user."
    architect = agent.split(":")[-1] == "architect"
    if rel.startswith(".bosun/") and not rel.startswith(".bosun/scratch/") and not architect:
        return ("the plan and task board belong to the manager. Put scratch files in .bosun/scratch/ "
                "and report changes in your BOSUN-RESULT instead.")
    cfg = load_config(project_dir(data))
    planning = cfg.get("planning") if isinstance(cfg.get("planning"), dict) else {}
    spec_dir = strip_dot_slash(normalize(str(planning.get("openspec_dir") or "openspec"))).strip("/") or "openspec"
    if not architect and any(rel == f"{spec_dir}/{entry}" or (entry.endswith("/") and rel.startswith(f"{spec_dir}/{entry}"))
                             for entry in OPENSPEC_ENTRIES):
        return ("OpenSpec files (proposal, specs, design, tasks.md) are the agreed spec; only the architect "
                "changes them, and the manager ticks tasks.md. Report spec gaps in your BOSUN-RESULT instead.")
    for pattern in cfg.get("protected_paths") or []:
        if isinstance(pattern, str) and matches(rel, pattern):
            return f"{rel} is a protected path in .bosun/config.json; ask the user before changing it."
    return None


# ----------------------------------------------------------------------------- events

def parse_result(message: str):
    if not message or RESULT_MARKER not in message:
        return None
    block = message[message.rfind(RESULT_MARKER):]
    result = {}
    for line in block.splitlines()[1:]:
        if line.strip().startswith("```"):
            break
        m = re.match(r"^([a-z_]+):\s*(.*?)\s*$", line)
        if m and m.group(1) not in result:
            value = re.sub(r"\s+#.*$", "", m.group(2)).strip().strip("'\"")
            result[m.group(1)] = value
    return result or None  # the marker mentioned in prose is not a result block


def log_event(data, event: str, result=None) -> None:
    root = project_dir(data)
    if not root:
        return
    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
        "agent_type": data.get("agent_type"),
        "agent_id": data.get("agent_id"),
        "session": str(data.get("session_id") or "")[:12],
    }
    if event == "stop":
        if result is None:
            entry["status"] = "no-result-block"
        else:
            for key in ("task", "status", "verdict", "branch", "commit"):
                if result.get(key):
                    entry[key] = result[key][:120]
            if result.get("summary"):
                entry["summary"] = result["summary"][:200]
    try:
        with open(os.path.join(root, ".bosun", "activity.jsonl"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def output_style(cfg) -> str:
    value = str(os.environ.get("BOSUN_OUTPUT_STYLE") or cfg.get("output_style") or "caveman").strip().lower()
    return value if value in STYLE_LEVELS or value == "normal" else "caveman"


def style_context(style: str):
    if style not in STYLE_LEVELS:
        return None
    lines = [f"[bosun] Output style: {style} (output_style in .bosun/config.json; normal turns it off).",
             f"- {STYLE_LEVELS[style]}"]
    lines += [f"- {rule}" for rule in STYLE_RULES]
    return "\n".join(lines)


def build_context(data):
    root = project_dir(data)
    cfg = load_config(root)
    style = style_context(output_style(cfg))
    room = MAX_CONTEXT_CHARS - len(style) - 2 if style else MAX_CONTEXT_CHARS
    profile = project_profile(root, cfg, room) if root else None
    if profile and style:
        return profile + "\n\n" + style
    return profile or style


def project_profile(root, cfg, limit=MAX_CONTEXT_CHARS):
    head = ["[bosun] Project profile from .bosun/config.json (project data; the manager's brief wins on conflict):"]
    commands = cfg.get("commands") or {}
    body = [f"- {name}: {value}" for name, value in commands.items() if isinstance(value, str) and value.strip()]
    body = body or ["- no commands configured: find them in package scripts, Makefile, or CI config"]
    conventions = cfg.get("conventions") or {}
    if conventions.get("commit_style"):
        body.append(f"- commit style: {conventions['commit_style']}")
    for note in (conventions.get("notes") or [])[:10]:
        body.append(f"- convention: {note}")
    tail = []
    protected = [p for p in cfg.get("protected_paths") or [] if isinstance(p, str)]
    if protected:
        tail.append("- protected paths (never edit): " + ", ".join(protected))
    tail.append(f"- main checkout: {root}")
    tail.append(f"Finish with the {RESULT_MARKER} block from your instructions.")
    lines = head + body + tail
    if len("\n".join(lines)) > limit:
        # Too long: drop the last free-form lines (convention notes first), never the protected paths,
        # the main checkout or the result reminder, and say that something was left out.
        cut = "- (profile cut to fit; the rest is in .bosun/config.json)"
        while body and len("\n".join(head + body + [cut] + tail)) > limit:
            body.pop()
        lines = head + body + [cut] + tail
    return "\n".join(lines)[:limit]


def handle(data):
    """Return (exit_code, stdout_text, stderr_text)."""
    event = data.get("hook_event_name")
    agent = str(data.get("agent_type") or "")
    if not agent.startswith(CREW_PREFIX):
        return 0, "", ""
    if event == "PreToolUse":
        if os.environ.get("BOSUN_GUARD", "1") == "0":
            return 0, "", ""
        tool = data.get("tool_name")
        tool_input = data.get("tool_input") or {}
        reason = None
        if tool == "Bash":
            reason = check_command(str(tool_input.get("command") or ""), is_isolated(data.get("cwd") or ""))
        elif tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
            target = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            reason = check_path(str(target), data, agent) if target else None
        if reason:
            return 2, "", f"bosun guard blocked this for {agent}: {reason}"
        return 0, "", ""
    if event == "SubagentStart":
        log_event(data, "start")
        context = build_context(data)
        if context:
            out = {"hookSpecificOutput": {"hookEventName": "SubagentStart", "additionalContext": context}}
            return 0, json.dumps(out), ""
        return 0, "", ""
    if event == "SubagentStop":
        result = parse_result(str(data.get("last_assistant_message") or ""))
        log_event(data, "stop", result)
        if result is None and not data.get("stop_hook_active") \
                and os.environ.get("BOSUN_ENFORCE_RESULT", "0") == "1":
            return 2, "", (f"End your final message with the {RESULT_MARKER} block from your instructions. "
                           "If you could not finish, report status blocked or failed and say why.")
        return 0, "", ""
    return 0, "", ""


def main() -> int:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            return 0
        code, out, err = handle(data)
    except Exception:  # fail open: never block the session because of a hook bug
        return 0
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
