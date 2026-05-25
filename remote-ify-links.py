#!/usr/bin/env python3
"""
Rewrite Cascade-style local file references in a Markdown file to GitHub URLs.

Two input shapes are recognized:

1. Cascade IDE link URIs (existing behaviour):

       [main.js](cci:7://file:///abs/path/main.js:0:0-0:0)
       [foo](cci:1://file:///abs/path/file.js:7:0-13:1)

2. Backticked citation references emitted by some Cascade prompt configs:

       `@/abs/path/main.js`              -> whole-file link
       `@/abs/path/main.js:42`           -> single-line link
       `@/abs/path/main.js:42-58`        -> range link

Both get rewritten to:

    [label](https://github.com/<owner>/<repo>/blob/<ref>/<relpath>[#L<a>[-L<b>]])

For citation references the label is computed: the file's basename is used
when that basename uniquely identifies a single relpath in the document
(common case), otherwise the full repo-relative path is used. A line-range
suffix like `:42-58` is appended to the label so the visible text matches the
original citation's information density.

By default <ref> is the current branch (`git branch --show-current`).
Override with --ref.

Repo URL (owner/repo) is cached in ~/.cache/remote-ify-links/cache.json
keyed by repo root path. Use --refresh-cache to re-read for the current repo.

Run the script from inside the target git repo (anywhere under its root).

Usage:
    remote-ify-links input.md                # print to stdout
    remote-ify-links input.md -o out.md
    remote-ify-links input.md --in-place
    remote-ify-links input.md --ref master
    remote-ify-links --refresh-cache         # re-read remote URL for this repo
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

CACHE_FILE = Path.home() / ".cache" / "remote-ify-links" / "cache.json"

# Matches [label](cci:N://file://<path>:L:C-L:C)
LINK_RE = re.compile(
    r"\[([^\]]+)\]\(cci:(\d+)://file://(.+?):(\d+):(\d+)-(\d+):(\d+)\)"
)

# Matches a backticked citation: `@/abs/path[:N[-M]]`
# Path component disallows backtick (terminator) and colon (line-range
# separator); both are unconventional in real filesystem paths.
CITATION_RE = re.compile(
    r"`@(/[^`:\s]+)(?::(\d+)(?:-(\d+))?)?`"
)


def run_git(*args: str, cwd: Path | None = None) -> str:
    """Run a git command and return stdout stripped, or '' on failure."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def parse_remote_url(url: str) -> tuple[str, str] | None:
    """
    Parse a GitHub remote URL into (owner, repo).

    Supports:
      git@github.com:owner/repo.git
      https://github.com/owner/repo.git
      https://github.com/owner/repo
      ssh://git@github.com/owner/repo.git
    """
    if not url:
        return None
    # Strip optional trailing .git
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    # git@github.com:owner/repo
    m = re.match(r"git@github\.com:([^/]+)/(.+)$", url)
    if m:
        return m.group(1), m.group(2)
    # https://github.com/owner/repo  or  ssh://git@github.com/owner/repo
    m = re.match(r"(?:https?|ssh)://(?:[^@]+@)?github\.com/([^/]+)/(.+)$", url)
    if m:
        return m.group(1), m.group(2)
    return None


def load_cache() -> dict:
    """Cache is a dict keyed by repo-root path → {remote_url, owner, repo}."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except json.JSONDecodeError:
            print(f"warning: cache file {CACHE_FILE} was unreadable; rebuilding",
                  file=sys.stderr)
    return {}


def save_cache(data: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, indent=2) + "\n")


def get_repo_root() -> Path:
    root = run_git("rev-parse", "--show-toplevel")
    if not root:
        sys.exit("error: not inside a git repository")
    return Path(root).resolve()


def get_repo_info(repo_root: Path, remote_name: str = "origin",
                  refresh: bool = False) -> tuple[str, str]:
    """Return (owner, repo) for the named remote in this repo.

    Cache key is `<repo_root>::<remote_name>` so different remotes within the
    same repo don't collide (e.g. `origin` -> upstream, `fork` -> personal).
    """
    key = f"{repo_root}::{remote_name}"
    cache = load_cache()
    entry = None if refresh else cache.get(key)
    if entry and "owner" in entry and "repo" in entry:
        return entry["owner"], entry["repo"]

    remote_url = run_git("remote", "get-url", remote_name, cwd=repo_root)
    if not remote_url:
        sys.exit(
            f"error: remote {remote_name!r} has no URL configured (or doesn't "
            f"exist). Configured remotes:\n"
            + (run_git("remote", "-v", cwd=repo_root) or "  (none)")
        )
    parsed = parse_remote_url(remote_url)
    if not parsed:
        sys.exit(
            f"error: could not parse GitHub URL from {remote_name!r} remote: "
            f"{remote_url!r}"
        )
    owner, repo = parsed
    cache[key] = {"remote_name": remote_name, "remote_url": remote_url,
                  "owner": owner, "repo": repo}
    save_cache(cache)
    return owner, repo


def get_current_branch() -> str:
    branch = run_git("branch", "--show-current")
    if not branch:
        sys.exit("error: could not determine current git branch (detached HEAD?). "
                 "Pass --ref explicitly.")
    return branch


def get_branch_remote(branch: str, repo_root: Path) -> str:
    """Return the configured push/tracking remote for `branch`, or empty string.

    Reads `branch.<name>.remote` from git config — the canonical answer for
    "where does this branch live?" once it has been pushed once with -u or
    explicitly configured. Returns '' if no upstream is set.
    """
    return run_git("config", f"branch.{branch}.remote", cwd=repo_root)


def build_github_url(owner: str, repo: str, ref: str, relpath: str,
                     start: int, end: int, is_range: bool) -> str:
    base = f"https://github.com/{owner}/{repo}/blob/{ref}/{relpath}"
    if not is_range:
        return base
    if start == end:
        return f"{base}#L{start}"
    return f"{base}#L{start}-L{end}"


def _resolve_in_repo(abs_path: str, repo_root: Path) -> str | None:
    """Return repo-relative POSIX path, or None if outside the repo."""
    try:
        return Path(abs_path).resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return None


def _basename_uniqueness(text: str, repo_root: Path) -> dict[str, bool]:
    """Scan citations in `text` and return {relpath: basename_is_unique}.

    A basename is "unique" when it maps to exactly one relpath across all
    repo-internal citations in the document.
    """
    basenames: dict[str, set[str]] = {}
    for m in CITATION_RE.finditer(text):
        relpath = _resolve_in_repo(m.group(1), repo_root)
        if relpath is None:
            continue
        bn = relpath.rsplit("/", 1)[-1]
        basenames.setdefault(bn, set()).add(relpath)

    unique: dict[str, bool] = {}
    for bn, paths in basenames.items():
        is_unique = len(paths) == 1
        for p in paths:
            unique[p] = is_unique
    return unique


def rewrite(text: str, owner: str, repo: str, ref: str, repo_root: Path) -> str:
    # Resolve once so symlinked roots (e.g. /tmp -> /private/tmp on macOS) and
    # `..` segments don't cause spurious "outside repo" misses when comparing
    # against `Path(abs_path).resolve()`.
    repo_root = repo_root.resolve()
    warnings: list[str] = []
    relpath_basename_unique = _basename_uniqueness(text, repo_root)

    def replace_link(match: re.Match) -> str:
        label, kind, abs_path, l1, _c1, l2, _c2 = match.groups()
        relpath = _resolve_in_repo(abs_path, repo_root)
        if relpath is None:
            warnings.append(f"skipped (outside repo): {abs_path}")
            return match.group(0)

        # cci:7 is a whole-file reference; cci:1 has a meaningful line range.
        is_range = kind == "1"
        url = build_github_url(
            owner, repo, ref, relpath, int(l1), int(l2), is_range
        )
        return f"[{label}]({url})"

    def replace_citation(match: re.Match) -> str:
        abs_path, l1, l2 = match.group(1), match.group(2), match.group(3)
        relpath = _resolve_in_repo(abs_path, repo_root)
        if relpath is None:
            warnings.append(f"skipped (outside repo): {abs_path}")
            return match.group(0)

        is_range = l1 is not None
        if is_range:
            start = int(l1)
            end = int(l2) if l2 is not None else start
        else:
            start = end = 0
        url = build_github_url(
            owner, repo, ref, relpath, start, end, is_range
        )

        # Smart label: basename when unambiguous in this doc, else relpath.
        # Append the original line-range so the visible text keeps the same
        # information density as the citation.
        basename = relpath.rsplit("/", 1)[-1]
        label_path = (
            basename if relpath_basename_unique.get(relpath, False) else relpath
        )
        if is_range:
            label = f"{label_path}:{start}" if start == end else f"{label_path}:{start}-{end}"
        else:
            label = label_path
        return f"[{label}]({url})"

    out = LINK_RE.sub(replace_link, text)
    out = CITATION_RE.sub(replace_citation, out)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    return out


def _pick_remote(repo_root: Path) -> str:
    """Auto-pick the remote to link against.

    Prefers the current branch's configured upstream remote (the place the
    branch is actually pushed to). Falls back to 'origin' with a stderr
    warning so PR-description links keep working from forks.
    """
    branch = run_git("branch", "--show-current", cwd=repo_root)
    if branch:
        configured = get_branch_remote(branch, repo_root)
        if configured:
            return configured
        print(
            f"warning: branch {branch!r} has no configured upstream remote; "
            f"falling back to 'origin'. If this branch lives on a fork, push "
            f"it with `git push -u <remote> {branch}` or pass --remote.",
            file=sys.stderr,
        )
    return "origin"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", help="Path to input markdown file. "
                                                 "Reads stdin if omitted.")
    parser.add_argument("-o", "--output", help="Output file (defaults to stdout)")
    parser.add_argument("--in-place", action="store_true",
                        help="Rewrite the input file in place")
    parser.add_argument("--ref", help="Git ref (branch/tag/SHA) to link against. "
                                      "Defaults to the current branch.")
    parser.add_argument("--remote", help="Remote name whose owner/repo should be "
                                          "used for the GitHub URL. Defaults to "
                                          "the current branch's configured "
                                          "upstream remote, falling back to "
                                          "'origin' if none is set.")
    parser.add_argument("--refresh-cache", action="store_true",
                        help="Re-read the remote URL even if cached")
    args = parser.parse_args()

    repo_root_for_refresh = None
    if args.refresh_cache and not args.input:
        # Just refresh and exit
        repo_root_for_refresh = get_repo_root()
        remote_name = args.remote or _pick_remote(repo_root_for_refresh)
        owner, repo = get_repo_info(repo_root_for_refresh, remote_name,
                                    refresh=True)
        print(f"Cached: {owner}/{repo} via remote {remote_name!r} "
              f"(root={repo_root_for_refresh})", file=sys.stderr)
        return

    if args.in_place and not args.input:
        sys.exit("error: --in-place requires an input file")
    if args.in_place and args.output:
        sys.exit("error: --in-place and --output are mutually exclusive")

    if args.input:
        text = Path(args.input).read_text()
    else:
        text = sys.stdin.read()

    repo_root = get_repo_root()
    remote_name = args.remote or _pick_remote(repo_root)
    owner, repo = get_repo_info(repo_root, remote_name,
                                refresh=args.refresh_cache)
    ref = args.ref or get_current_branch()

    rewritten = rewrite(text, owner, repo, ref, repo_root)

    if args.in_place:
        Path(args.input).write_text(rewritten)
    elif args.output:
        Path(args.output).write_text(rewritten)
    else:
        sys.stdout.write(rewritten)


if __name__ == "__main__":
    main()
