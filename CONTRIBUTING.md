# Contributing

## Workflow

- Open an issue with the problem, scope and acceptance criteria. Never include API keys, private endpoints or unredacted request logs.
- Use focused feat/, fix/ or docs/ branches and descriptive feat:, fix:, docs: or chore: commits.
- Link the issue in a pull request and explain the changed behavior, validation and remaining limitations.
- main contains reviewed project work; workflow conventions are not enforced branch protection.

## Validation

- Basic checks validates Python syntax on Python 3.12, JavaScript syntax and shell syntax. It makes no model or relay calls and needs no secrets.
- Changes to relay behavior require separate authorized runtime checks with recorded configuration and sanitized evidence.
- Verify macOS launch and packaging changes on macOS. Linux syntax checks do not validate the app bundle.
- Matching response metadata cannot prove the identity of an upstream model.

## Environment and data

- Preserve existing valid environments. On 64-bit Windows, use 64-bit CPython and verify its executable, version and pointer width before creating environments or installing packages. Never silently fall back to 32-bit Python.
- Keep local credentials, generated reports and environment directories out of Git. Review artifacts before intentionally committing them.
- Preserve the MIT license and document third-party sources and licenses when adding dependencies or assets.
