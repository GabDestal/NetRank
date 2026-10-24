"""Execute demo.ipynb in place against the local stack, so its committed outputs are current (make notebook).

The notebook never calls Groq: its agent cells replay recorded or scripted model turns.
"""

import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

NOTEBOOK = Path("demo.ipynb")


def main() -> None:
    """Run every cell from the repository root and save the outputs."""
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else NOTEBOOK
    notebook = nbformat.read(path, as_version=4)
    NotebookClient(notebook, timeout=600, kernel_name="python3", resources={"metadata": {"path": "."}}).execute()
    with path.open("w", encoding="utf-8", newline="\n") as handle:  # LF on Windows too (end-of-file hooks)
        nbformat.write(notebook, handle)


if __name__ == "__main__":
    main()
