"""Build the public Pages artifact without copying private report workspaces."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


STATIC_SUFFIXES = {
    ".html", ".htm", ".css", ".js", ".mjs",
    ".avif", ".webp", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".otf",
}


class BuildError(ValueError):
    pass


def public_files(source: Path) -> list[Path]:
    homepage = source / "index.html"
    previews = source / "previews"
    if homepage.is_symlink() or not homepage.is_file():
        raise BuildError("The landing page must be a regular index.html file")
    if previews.is_symlink() or not previews.is_dir():
        raise BuildError("The curated previews directory is missing or is a symlink")
    if not (previews / "index.html").is_file():
        raise BuildError("The preview directory page is missing")
    files = [homepage]
    for path in sorted(previews.rglob("*")):
        relative = path.relative_to(source)
        if path.is_symlink():
            raise BuildError(f"Public files must not be symlinks: {relative}")
        if any(part.startswith(".") for part in relative.parts):
            raise BuildError(f"Hidden paths are not public assets: {relative}")
        if path.is_dir():
            continue
        if not path.is_file() or path.suffix.lower() not in STATIC_SUFFIXES:
            raise BuildError(f"Unsupported public asset: {relative}")
        files.append(path)
    return files


def build_site(source: Path, destination: Path) -> int:
    source = source.resolve()
    destination = destination.resolve()
    if source.is_relative_to(destination) or destination.is_relative_to(source / "previews"):
        raise BuildError("Output must not replace the source or sit inside previews")
    files = public_files(source)
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise BuildError("Output must be an empty or new directory; existing files were not changed")
    destination.mkdir(parents=True, exist_ok=True)
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    (destination / ".nojekyll").write_text("", encoding="utf-8")
    return len(files)


def main() -> int:
    source = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=source / "_site")
    args = parser.parse_args()
    try:
        count = build_site(source, args.output)
    except (BuildError, OSError) as exc:
        print(f"Static site build failed: {exc}", file=sys.stderr)
        return 1
    print(f"Prepared {count} public files in {args.output}. Private reports were not included.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
