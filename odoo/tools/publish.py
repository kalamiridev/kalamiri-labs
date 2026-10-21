"""Release Odoo modules from this repository to the release repository (e.g. odoo-croatia, branch 19.0).

    python publish.py <release repository> <module> [<module> ...]

Copies each module (without internal notes and caches) to the root of the release repository,
updates the module list in its README.md and commits it with the source commit of this repository.
Nothing is pushed. The release repository is never edited by hand.
"""
import ast
import re
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
IGNORE = shutil.ignore_patterns("CLAUDE.md", "CLAUDE.local.md", "__pycache__", "*.pyc", ".pytest_cache")
REQUIRED = ("__manifest__.py", "README.md", "LICENSE", "static/description/icon.png", "static/description/index.html")
MARKERS = ("<!-- modules -->", "<!-- /modules -->")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def manifest(path):
    return ast.literal_eval((path / "__manifest__.py").read_text(encoding="utf-8"))


def check(name):
    path = SOURCE / name
    missing = [item for item in REQUIRED if not (path / item).exists()]
    if missing:
        sys.exit(f"{name}: missing {', '.join(missing)}")
    if git(SOURCE, "status", "--porcelain", "--", name):
        sys.exit(f"{name}: has uncommitted changes in kalamiri-labs; commit them first")
    return manifest(path)


def module_table(target):
    rows = ["| Module | Version | Description |", "|---|---|---|"]
    for path in sorted(p for p in target.iterdir() if (p / "__manifest__.py").exists()):
        data = manifest(path)
        rows.append(f"| [`{path.name}`](./{path.name}/) | {data['version']} | {data.get('summary', data['name'])} |")
    return "\n".join(rows)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    target = Path(sys.argv[1]).resolve()
    names = sys.argv[2:]
    manifests = {name: check(name) for name in names}
    for name in names:
        shutil.rmtree(target / name, ignore_errors=True)
        shutil.copytree(SOURCE / name, target / name, ignore=IGNORE)
    readme = target / "README.md"
    text = readme.read_text(encoding="utf-8")
    start, end = text.index(MARKERS[0]) + len(MARKERS[0]), text.index(MARKERS[1])
    readme.write_text(text[:start] + "\n" + module_table(target) + "\n" + text[end:], encoding="utf-8", newline="\n")
    source_commit = git(SOURCE, "rev-parse", "--short", "HEAD")
    git(target, "add", "-A", "--", *names, "README.md")
    if not git(target, "status", "--porcelain"):
        print("Nothing changed.")
        return
    title = ", ".join(f"{name} {manifests[name]['version']}" for name in names)
    git(target, "commit", "-q", "-m", f"{title}\n\nReleased from kalamiri-labs {source_commit}.")
    print(f"Committed in {target}: {title} (from kalamiri-labs {source_commit}). Not pushed.")


if __name__ == "__main__":
    main()
