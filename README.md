# remote-ify-links

Rewrite Cascade-style local file links in a Markdown file to GitHub URLs.

Useful for fixing up PR descriptions drafted with the help of Cascade (or any
tool that emits links like `[label](cci:7://file:///abs/path/file.js:...)`),
turning them into real `https://github.com/owner/repo/blob/...` links.

## Requirements

- Python 3.10+ (uses `tuple[str, str]` syntax). No third-party packages.
- `git` on `$PATH`.

## Install

1. Clone this repo wherever you keep tools:

   ```sh
   git clone https://github.com/ejones23/remote-ify-links.git
   ```

2. Make the script available as a command. Pick whichever style fits your
   workflow — the script is self-contained, so any of these work:

   - **Symlink into a directory on your `$PATH`** (e.g. `~/.local/bin`,
     `~/bin`, `/usr/local/bin`):
     ```sh
     ln -s "$(pwd)/remote-ify-links/remote-ify-links.py" /path/on/your/PATH/remote-ify-links
     ```
   - **Add a shell alias** in your shell rc file:
     ```sh
     alias remote-ify-links="python3 /full/path/to/remote-ify-links/remote-ify-links.py"
     ```
   - **Add the repo directory to your `$PATH`** and rename or symlink the
     script to drop the `.py` extension if you prefer.
   - **Just invoke it directly** with `python3 /path/to/remote-ify-links.py`.

   Whichever approach you use, the only requirement is that you can invoke the
   script from inside any git repo where you want to rewrite links.

## Usage

Run the script from anywhere inside the git repo whose links you want to
rewrite. The current branch is auto-detected as the link ref.

```sh
remote-ify-links input.md                # print to stdout
remote-ify-links input.md -o out.md      # write to a new file
remote-ify-links input.md --in-place     # rewrite in place
remote-ify-links input.md --ref master   # use a specific branch/tag/SHA
cat input.md | remote-ify-links          # read from stdin
remote-ify-links --refresh-cache         # re-read this repo's origin URL
```

## What it does

Two link shapes are recognized:

| Cascade format | Becomes |
|---|---|
| `[label](cci:7://file:///abs/path:0:0-0:0)` | `[label](https://github.com/owner/repo/blob/<ref>/relpath)` |
| `[label](cci:1://file:///abs/path:L1:C1-L2:C2)` | `[label](https://github.com/owner/repo/blob/<ref>/relpath#L<L1>-L<L2>)` |

- `cci:7` is a whole-file reference; the trailing `:0:0-0:0` is dropped.
- `cci:1` is a symbol/range reference. GitHub only supports line ranges, so
  column information is dropped. Single-line ranges become `#L<n>` instead of
  `#L<n>-L<n>`.
- Links to paths outside the current repo are left unchanged (with a warning
  to stderr).
- Links already pointing at `https://github.com/...` are left unchanged.

## Cache

Per-repo origin URL info is cached in `~/.cache/remote-ify-links/cache.json`,
keyed by the repo's root path. The cache survives across multiple repos. To
rebuild it for the current repo, run with `--refresh-cache`.

## License

MIT — do whatever you want with it.
