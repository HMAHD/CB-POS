# Developer Onboarding Guide

Welcome to the CB POS team! This guide will help you set up your development environment.

## Prerequisites

- Python 3.12+
- Git

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ceylonbyte/cbpos.git
    cd cbpos
    ```

2.  **Install [uv](https://docs.astral.sh/uv/):**
    ```bash
    # Windows
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    # Linux/Mac
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

3.  **Install dependencies:**
    ```bash
    uv sync
    ```
    Creates `.venv` and installs the exact versions from `uv.lock`. No activation needed — prefix commands with `uv run`.

4.  **Install pre-commit hooks:**
    ```bash
    uv run pre-commit install
    ```

5.  **Seed the database:**
    ```bash
    uv run python scripts/seed.py
    ```

6.  **Run the application:**
    ```bash
    uv run python main.py
    ```

## Project Structure

- `cbpos/core`: Business logic, models, and services.
- `cbpos/infrastructure`: Hardware drivers, logging, and external systems.
- `cbpos/ui`: PyQt6 views, widgets, and resources.
- `tests`: Unit and integration tests.
