"""The README Makefile table and `make help` list the same targets with the same descriptions."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def help_targets() -> dict[str, str]:
    """Targets and descriptions as `make help` prints them (the `## ` comments of the Makefile)."""
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    return dict(re.findall(r"^([a-z-]+):.*?## (.*)$", text, re.M))


def readme_targets() -> dict[str, str]:
    """Targets and descriptions of the README Makefile table, code spans unwrapped."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = text[text.index("## Makefile") :].split("\n## ", 1)[0]
    rows = re.findall(r"^\| `make ([a-z-]+)` \| (.*) \|$", section, re.M)
    return {target: description.replace("`", "") for target, description in rows}


def test_readme_makefile_table_matches_make_help():
    """Same targets, same order, same descriptions: a new or renamed target must be documented."""
    assert list(readme_targets().items()) == list(help_targets().items())


def test_every_help_target_is_phony():
    """Each documented target is declared .PHONY, so a file of the same name never shadows it."""
    phony = re.search(r"^\.PHONY:(.*)$", (ROOT / "Makefile").read_text(encoding="utf-8"), re.M).group(1).split()
    assert set(help_targets()) <= set(phony)
