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

2.  **Create a virtual environment:**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Linux/Mac
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Install pre-commit hooks:**
    ```bash
    pre-commit install
    ```

5.  **Seed the database:**
    ```bash
    python scripts/seed.py
    ```

6.  **Run the application:**
    ```bash
    python main.py
    ```

## Project Structure

- `cbpos/core`: Business logic, models, and services.
- `cbpos/infrastructure`: Hardware drivers, logging, and external systems.
- `cbpos/ui`: PyQt6 views, widgets, and resources.
- `tests`: Unit and integration tests.
