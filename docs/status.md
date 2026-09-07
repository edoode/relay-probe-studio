# Project status

Updated: 2026-09-07.

## Current scope

The repository contains a Python relay probing engine, a local web UI and macOS launch/build scripts. It is public and uses the MIT license. Existing source code and the license were preserved during the repository-management update.

## Validation boundary

Basic checks parses all tracked Python files with Python 3.12, checks web/app.js with Node and parses the launcher scripts with Bash. These checks do not call models, verify upstream model identity, test credentials or validate the macOS app bundle.

No live relay requests or macOS runtime/package tests were performed as part of this management update. The README privacy description now explicitly includes the configured relay as a recipient of the API Authorization header, consistent with the existing code.

## Next work

- Record reproducible macOS startup and packaging checks with OS and runtime versions.
- Establish sanitized representative cases for model listing, remapping, malformed responses and timeouts.
- Record evidence and limitations before creating a versioned release.

Use [Issues](https://github.com/edoode/relay-probe-studio/issues) for task status and acceptance evidence.
