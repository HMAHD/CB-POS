import subprocess
import sys
import os

def install_dependencies():
    print("Installing development dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "black", "flake8"])

def create_config_files():
    print("Creating configuration files...")
    
    # pyproject.toml for Black
    pyproject_content = """
[tool.black]
line-length = 88
target-version = ['py312']
include = '\.pyi?$'
exclude = '''
/(
    \.eggs
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | _build
  | buck-out
  | build
  | dist
)/
'''
"""
    with open("pyproject.toml", "w") as f:
        f.write(pyproject_content.strip())
        
    # .flake8 for Flake8
    flake8_content = """
[flake8]
max-line-length = 88
extend-ignore = E203
exclude = .git,__pycache__,docs/source/conf.py,old,build,dist,.venv
"""
    with open(".flake8", "w") as f:
        f.write(flake8_content.strip())

def main():
    try:
        install_dependencies()
        create_config_files()
        print("Development environment setup complete.")
    except Exception as e:
        print(f"Setup failed: {e}")

if __name__ == "__main__":
    main()
