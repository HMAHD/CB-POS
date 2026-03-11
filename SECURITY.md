# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.2.x   | :white_check_mark: |
| 1.1.x   | :white_check_mark: |
| 1.0.x   | :x:                |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in CB POS, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. **Email**: Send a detailed report to the repository owner via GitHub private messaging or the contact information listed on the [Ceylon Byte website](https://ceybyte.com).

2. **Include the following information**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: We will acknowledge receipt of your report within **48 hours**.
- **Assessment**: We will investigate and assess the severity within **7 days**.
- **Fix**: Critical vulnerabilities will be patched as soon as possible, typically within **14 days**.
- **Disclosure**: We will coordinate with you on public disclosure timing after the fix is released.

### Scope

The following are in scope for security reports:

- Authentication bypass or privilege escalation
- SQL injection or data exposure
- PIN/credential storage weaknesses
- Unauthorized access to audit logs or financial data
- Vulnerabilities in the database layer (SQLite/PostgreSQL)
- Printer driver command injection

### Out of Scope

- Issues requiring physical access to the terminal
- Denial of service on local SQLite database
- Social engineering attacks
- Issues in third-party dependencies (report those to the respective projects)

## Security Best Practices for Deployment

- Always change default PINs (`admin`/`1234`, `cashier`/`0000`) after initial setup
- Enable session timeout in settings to auto-logout inactive terminals
- Use PostgreSQL mode with proper credentials for multi-terminal deployments
- Regularly backup your database using the built-in backup feature
- Keep CB POS updated to the latest supported version
