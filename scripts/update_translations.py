import os
import subprocess


def update_translations():
    """
    Runs pylupdate6 to scan all .py files and generate .ts files.
    """
    # Base directory (project root)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Target directory for translations
    translations_dir = os.path.join(
        base_dir, "cbpos", "ui", "resources", "translations"
    )

    if not os.path.exists(translations_dir):
        os.makedirs(translations_dir)
        print(f"Created directory: {translations_dir}")

    # Source files (all .py files in cbpos)
    source_files = []
    for root, _, files in os.walk(os.path.join(base_dir, "cbpos")):
        for file in files:
            if file.endswith(".py"):
                source_files.append(os.path.join(root, file))

    if not source_files:
        print("No source files found.")
        return

    # Target TS files
    ts_files = [
        os.path.join(translations_dir, "cbpos_si.ts"),
        os.path.join(translations_dir, "cbpos_ta.ts"),
    ]

    print(f"Found {len(source_files)} source files.")

    # Run pylupdate6 for each TS file
    for ts_file in ts_files:
        # Construct command
        # pylupdate6 [source_files] -ts [ts_file]
        cmd = ["pylupdate6"] + source_files + ["-ts", ts_file]

        print(f"Updating {os.path.basename(ts_file)}...")
        try:
            subprocess.run(cmd, check=True)
            print(f"Successfully updated {os.path.basename(ts_file)}")
        except subprocess.CalledProcessError as e:
            print(f"Error updating {os.path.basename(ts_file)}: {e}")
        except FileNotFoundError:
            print(
                "Error: pylupdate6 not found. Please install PyQt6 tools (pip install PyQt6)."
            )
            return


if __name__ == "__main__":
    update_translations()
