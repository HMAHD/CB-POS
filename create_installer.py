import subprocess
import os
import shutil


def create_installer():
    print("🚀 Starting Build Process...")

    # Clean previous builds
    if os.path.exists("dist"):
        shutil.rmtree("dist")
    if os.path.exists("build"):
        shutil.rmtree("build")

    print("🧹 Cleaned previous builds.")

    # Run PyInstaller
    print("📦 Running PyInstaller...")
    result = subprocess.run(
        ["pyinstaller", "--clean", "cbpos.spec"], capture_output=True, text=True
    )

    if result.returncode == 0:
        print("✅ Build Successful!")
        print(f"Output: {os.path.abspath('dist/cbpos.exe')}")
    else:
        print("❌ Build Failed!")
        print(result.stderr)


if __name__ == "__main__":
    create_installer()
