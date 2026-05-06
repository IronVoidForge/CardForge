from __future__ import annotations

from pathlib import Path

ROOTS = [Path("src"), Path("tests"), Path("scripts")]
TEXT_SUFFIXES = {".py", ".md", ".txt", ".toml", ".yml", ".yaml", ".html", ".css"}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for root in ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)
    return sorted(files)


def main() -> int:
    failures: list[str] = []
    for path in iter_files():
        text = path.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            failures.append(f"{path}: missing trailing newline")
        for index, line in enumerate(text.splitlines(), start=1):
            if line.rstrip() != line:
                failures.append(f"{path}:{index}: trailing whitespace")
            if "\t" in line:
                failures.append(f"{path}:{index}: tab character")
    if failures:
        print("Format check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print(f"Format check passed for {len(iter_files())} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
