"""
Convenience launcher for the FastAPI dashboard.
Double-click or run this file to start web_app.py using the local virtualenv.
"""

import subprocess
import sys
import webbrowser
from pathlib import Path


def find_project_dir(base_dir: Path) -> Path | None:
    """
    Try to locate the project folder regardless of where the launcher is run from.
    """
    candidates = [
        base_dir / "auto-emailer-linkedin",
        base_dir.parent / "auto-emailer-linkedin",
        base_dir,  # in case the launcher is placed inside the project folder
    ]
    for c in candidates:
        if (c / "web_app.py").exists():
            return c
    return None


def find_python(project_dir: Path) -> Path:
    """
    Prefer the project's virtualenv interpreter; fall back to the current Python.
    """
    venv_candidates = [
        project_dir / ".venv" / "Scripts" / "python.exe",  # Windows
        project_dir.parent / ".venv" / "Scripts" / "python.exe",
        project_dir / ".venv" / "bin" / "python",  # macOS/Linux
        project_dir.parent / ".venv" / "bin" / "python",
    ]
    for cand in venv_candidates:
        if cand.exists():
            return cand
    return Path(sys.executable)


def main():
    # When frozen by PyInstaller, __file__ points inside the bundle; use sys.executable for the exe location
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    project_dir = find_project_dir(base_dir)

    if project_dir is None:
        print("Could not find the project folder (auto-emailer-linkedin). Make sure it sits next to this launcher.")
        sys.exit(1)

    python_cmd = find_python(project_dir)

    print(f"Using interpreter: {python_cmd}")
    print(f"Starting web_app.py in {project_dir} ...")

    proc = subprocess.Popen([str(python_cmd), "web_app.py"], cwd=project_dir)
    try:
        webbrowser.open("http://127.0.0.1:8000")
    except Exception:
        pass
    proc.wait()


if __name__ == "__main__":
    main()
