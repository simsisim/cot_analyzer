#!/usr/bin/env python3
"""
run_batch.py
Orchestrator for processing multiple COT analysis runs based on batching.csv.
"""

import csv
import subprocess
import sys
from pathlib import Path

def main():
    project_root = Path(__file__).parent.parent
    main_py = project_root / "main.py"

    # Allow custom batch file as 1st argument
    if len(sys.argv) > 1:
        batch_file = Path(sys.argv[1]).resolve()
    else:
        batch_file = project_root / "user_input" / "batching.csv"

    if not batch_file.exists():
        print(f"Error: {batch_file} not found.")
        sys.exit(1)

    # Read batching config
    runs = []
    with batch_file.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name   = row.get("name", "").strip()
            range_ = row.get("chart_display_range", "").strip()
            tag    = row.get("foldername_suffix_tag", "").strip()
            if name:
                runs.append((name, range_, tag))

    if not runs:
        print("No valid runs found in batching.csv.")
        sys.exit(0)

    print(f"Starting batch process: {len(runs)} items found.\n")

    for i, (name, date_range, tag) in enumerate(runs, 1):
        print(f"[{i}/{len(runs)}] Processing: {name}")
        print(f"      Range : {date_range}")
        print(f"      Tag   : {tag}")
        
        cmd = [
            sys.executable, str(main_py),
            "--instrument", name,
        ]
        if date_range:
            cmd.extend(["--range", date_range])
        if tag:
            # Strip leading underscore if user provided it, as loader.py adds its own formatting logic
            tag_clean = tag.lstrip("_")
            cmd.extend(["--tag", tag_clean])

        try:
            # Run main.py and wait for completion
            result = subprocess.run(cmd, check=True, capture_output=False)
            print(f"      Success.\n")
        except subprocess.CalledProcessError as e:
            print(f"      FAILED with exit code {e.returncode}.\n")

    print("Batch processing complete.")

if __name__ == "__main__":
    main()
