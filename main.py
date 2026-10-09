"""Great Sage AI Assistant - Entry Point."""
import os
import sys

# Ensure UTF-8 output on Windows
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if getattr(sys.stdout, "reconfigure", None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sage_app import main

if __name__ == "__main__":
    main()