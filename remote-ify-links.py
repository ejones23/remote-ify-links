#!/usr/bin/env python3
"""
Rewrite Cascade-style local file links in a Markdown file to GitHub URLs.

Cascade emits links like:

    [main.js](cci:7://file:///abs/path/main.js:0:0-0:0)
    [foo](cci:1://file:///abs/path/file.js:7:0-13:1)

This script rewrites them to:

    [main.js](https://github.com/<owner>/<repo>/blob/<ref>/<relpath>)
    [foo](https://github.com/<owner>/<repo>/blob/<ref>/<relpath>#L7-L13)

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


def get_repo_info(repo_root: Path, refresh: bool = False) -> tuple[str, str]:
    """Return (owner, repo) for the given repo root, using the cache when available."""
    key = str(repo_root)
    cache = load_cache()
    entry = None if refresh else cache.get(key)
    if entry and "owner" in entry and "repo" in entry:
        return entry["owner"], entry["repo"]

    remote = run_git("remote", "get-url", "origin", cwd=repo_root)
    parsed = parse_remote_url(remote)
    if not parsed:
        sys.exit(f"error: could not parse GitHub URL from origin remote: {remote!r}")
    owner, repo = parsed
    cache[key] = {"remote_url": remote, "owner": owner, "repo": repo}
    save_cache(cache)
    return owner, repo


def get_current_branch() -> str:
    branch = run_git("branch", "--show-current")
    if not branch:
        sys.exit("error: could not determine current git branch (detached HEAD?). "
                 "Pass --ref explicitly.")
    return branch


def build_github_url(owner: str, repo: str, ref: str, relpath: str,
                     start: int, end: int, is_range: bool) -> str:
    base = f"https://github.com/{owner}/{repo}/blob/{ref}/{relpath}"
    if not is_range:
        return base
    if start == end:
        return f"{base}#L{start}"
    return f"{base}#L{start}-L{end}"


def rewrite(text: str, owner: str, repo: str, ref: str, repo_root: Path) -> str:
    warnings: list[str] = []

    def replace(match: re.Match) -> str:
        label, kind, abs_path, l1, _c1, l2, _c2 = match.groups()
        abs_path_obj = Path(abs_path).resolve()
        try:
            relpath = abs_path_obj.relative_to(repo_root).as_posix()
        except ValueError:
            warnings.append(
                f"skipped (outside repo): {abs_path}"
            )
            return match.group(0)

        # cci:7 is a whole-file reference; cci:1 has a meaningful line range.
        is_range = kind == "1"
        url = build_github_url(
            owner, repo, ref, relpath, int(l1), int(l2), is_range
        )
        return f"[{label}]({url})"

    out = LINK_RE.sub(replace, text)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    return out


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
    parser.add_argument("--refresh-cache", action="store_true",
                        help="Re-read origin remote URL even if cached")
    args = parser.parse_args()

    if args.refresh_cache and not args.input:
        # Just refresh and exit
        repo_root = get_repo_root()
        owner, repo = get_repo_info(repo_root, refresh=True)
        print(f"Cached: {owner}/{repo} (root={repo_root})", file=sys.stderr)
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
    owner, repo = get_repo_info(repo_root, refresh=args.refresh_cache)
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
