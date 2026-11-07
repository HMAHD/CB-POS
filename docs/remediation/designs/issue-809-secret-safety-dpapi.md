# Security Design Note: Issue #809 — Random Encryption Keys and DPAPI Protection

## Context & Problem
CB POS encrypts sensitive settings (`network_db_password`, `smtp_pass`, `sync_shared_secret`, `sync_pinned_cert_pem`) and the shop backup password (`.backup_password`) using Fernet symmetric encryption.
Previously, `ConfigService._get_fernet()` generated the key as `sha256("cbpos-{hostname}-{system}")` when `.encryption_key` was missing. Anyone knowing the PC name and OS could decrypt sensitive credentials from `settings.json` or backups.

## Target Architecture

### 1. Key Generation
- On fresh install or when generating a replacement key, call `Fernet.generate_key()`.
- Never use `platform.node()`, `platform.system()`, or any machine metadata to derive new encryption keys.

### 2. Key Storage & At-Rest Protection
- Storage format in `.encryption_key`:
  - Windows (`sys.platform == 'win32'`): `dpapi:<base64-blob>` wrapped via user-scoped DPAPI:
    ```python
    blob = win32crypt.CryptProtectData(key, "CB POS", None, None, None, 1)  # 1 = CRYPTPROTECT_UI_FORBIDDEN
    stored = f"dpapi:{base64.b64encode(blob).decode('ascii')}"
    ```
    Unwrapping:
    ```python
    blob = base64.b64decode(payload)
    _, key = win32crypt.CryptUnprotectData(blob, None, None, None, 1)
    ```
  - Other OSes (Linux, macOS): `raw:<base64-fernet-key>` with `0600` file permissions (`_write_restricted`).
- If unwrap fails (`CryptUnprotectData` raises `pywintypes.error` / `OSError`, or `dpapi:` prefix found on non-Windows without `win32crypt`, or corrupted/0-byte key):
  - Quarantine the unreadable key file: rename it to `.encryption_key.corrupt-<timestamp>`.
  - Generate a new random key and save it (`dpapi:` or `raw:`).
  - Mark sensitive keys as undecryptable (`_undecryptable_keys`), triggering the established #875 re-entry notice.
  - Never fallback to hostname derivation. Never erase non-secret settings.

### 3. One-Time Legacy Migration
- `_derive_legacy_hostname_key()` is retained strictly inside migration logic for backwards compatibility.
- Migration triggers during `ConfigService.load()` (or when initializing Fernet before reading sensitive data) when:
  a. `.encryption_key` has no prefix (`raw:` or `dpapi:`), or
  b. `.encryption_key` is missing and stored ciphertext settings decrypt successfully using the hostname-derived key.
- Migration workflow:
  1. Determine the legacy key:
     - If `.encryption_key` exists without a prefix, read its trimmed ASCII content as the legacy key.
     - If missing, compute `_derive_legacy_hostname_key()`.
  2. Decrypt all sensitive settings in `settings.json` using the legacy key.
  3. If `.backup_password` exists:
     - Decrypt it using the legacy key.
  4. Generate a new cryptographically random key via `Fernet.generate_key()`.
  5. Re-encrypt all sensitive settings using the new key.
  6. If `.backup_password` was present and decrypted:
     - Re-encrypt the password token with the new key and write it atomically to `_BACKUP_PASSWORD_FILE` using `_write_restricted`.
  7. Write the new protected key file (`dpapi:` on Windows, `raw:` on other platforms) atomically using `_write_restricted`.
  8. Atomically persist `settings.json` and `settings.json.bak` with the re-encrypted values (via `ConfigService.save()`).
  9. Log only `INFO: Settings encryption key upgraded` (zero key or secret material logged).

### 4. Security Invariants
- No key material, plaintext passwords, tokens, or decrypted settings logged at any log level.
- Atomic writes for settings, backup password, and key files to avoid partial or corrupted state.
- Windows user-scoped DPAPI prevents other local users from decrypting key material.
- If unwrap or decryption fails, never crash; quarantine unreadable key and trigger #875 re-entry.
