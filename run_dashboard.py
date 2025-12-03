"""
Convenience launcher for the FastAPI dashboard.
Double-click or run this file to start web_app.py using the local virtualenv.

Build an exe (name: LinkedInEmailer) with PyInstaller:
  Windows: pyinstaller --onefile --noconsole --name LinkedInEmailer run_dashboard.py
  macOS:   pyinstaller --onefile --windowed --name LinkedInEmailer run_dashboard.py
"""

import os
import subprocess
import sys
import webbrowser
from pathlib import Path


def find_project_dir(base_dir: Path) -> Path | None:
    """
    Try to locate the project folder regardless of where the launcher is run from.
    """
    names = [
        "auto-emailer-linkedin",
        "LinkedIn-Post-Emailer",
        "LinkedIn-Post-Emailer-main",
    ]
    candidates = [base_dir] + [base_dir / n for n in names] + [base_dir.parent / n for n in names] + [base_dir.parent]
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


def build_exe_if_missing(base_dir: Path, python_cmd: Path):
    """
    If dist/LinkedInEmailer(.exe) is missing, attempt to build it with PyInstaller.
    """
    dist_dir = base_dir / "dist"
    target = dist_dir / ("LinkedInEmailer.exe" if os.name == "nt" else "LinkedInEmailer")
    if target.exists():
        return

    if getattr(sys, "frozen", False):
        return  # already running as an exe; don't rebuild

    try:
        print("Building LinkedInEmailer executable with PyInstaller (this may take a minute)...")
        subprocess.check_call(
            [
                str(python_cmd),
                "-m",
                "PyInstaller",
                "--onefile",
                "--noconsole" if os.name == "nt" else "--windowed",
                "--name",
                "LinkedInEmailer",
                "run_dashboard.py",
            ],
            cwd=base_dir,
        )
        print(f"Built executable at: {target}")
    except Exception as e:
        print(
            "PyInstaller build failed. Ensure pyinstaller is installed "
            "(pip install pyinstaller) and retry. Error:",
            e,
        )


def bootstrap_venv(project_dir: Path) -> Path:
    """
    Create .venv and install dependencies if missing. Returns the venv python path.
    """
    venv_dir = project_dir / ".venv"
    venv_python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    if not venv_python.exists():
        print("Creating virtualenv ...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])

    requirements = project_dir / "requirements.txt"
    if requirements.exists():
        print("Installing dependencies ...")
        subprocess.check_call([str(venv_python), "-m", "pip", "install", "-r", str(requirements)])
    else:
        print("requirements.txt not found; skipping dependency install.")

    return venv_python


def main():
    # When frozen by PyInstaller, __file__ points inside the bundle; use sys.executable for the exe location
    base_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    project_dir = find_project_dir(base_dir)

    if project_dir is None:
        print(
            "Could not find the project folder. Ensure this launcher sits next to or inside one of:\n"
            "- auto-emailer-linkedin\n- LinkedIn-Post-Emailer\n- LinkedIn-Post-Emailer-main"
        )
        sys.exit(1)

    python_cmd = find_python(project_dir)

    if not python_cmd.exists():
        python_cmd = bootstrap_venv(project_dir)

    # Attempt to build the standalone exe if it's not present
    build_exe_if_missing(base_dir, python_cmd)

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
