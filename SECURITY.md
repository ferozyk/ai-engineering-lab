# Security Policy

## Reporting a vulnerability

Open a private security advisory from the repository's Security tab on GitHub. Do not open public issues for vulnerabilities.

## Secrets handling

- Secrets live only in a local `.env` file or the shell environment; `.env` is gitignored.
- Credentials are held as `SecretStr`, so they are masked when settings are printed or serialised. Code must still never log raw secret values.
- Secrets must never be logged, committed or included in documentation.

## Synthetic data only

Experiments use synthetic data. Never use real banking or customer data, real credentials or production systems.

## Generated-code execution

Code produced by a model must never run directly on the host. Execution requires a sandbox with:

- Filesystem restrictions
- Network restrictions
- Resource limits
- Execution timeouts
- Restricted credentials
- Explicit tool allowlists

## Authorization

Authorization is enforced by application code, never delegated to the model.

## Supported versions

Only the `master` branch is supported. This is a lab, not a product.
