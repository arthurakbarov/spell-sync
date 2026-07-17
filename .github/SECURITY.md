# Security

spell-sync is a **local** CLI. It does not send data over the network, run a server, or execute
remote code. It reads and writes spell-check dictionary files on your machine when you run commands
(`pull`, `push`, and others).

## Reporting a vulnerability

Report security issues privately via
[GitHub Security Advisories](https://github.com/arthurakbarov/spell-sync/security/advisories/new).

Do not post exploit details in public issues before a fix is available.

See also [Contributing](../docs/CONTRIBUTING.md#security).

## Permissions

On macOS, writing some system dictionary paths may require **Full Disk Access** for your terminal.
That is an OS permission model, not network exposure.
