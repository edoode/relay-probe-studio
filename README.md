# Relay Probe Studio

Apple-style local UI for verifying whether an OpenAI-compatible relay really supports a target model, whether the route is stable, and whether the returned metadata matches what the relay claims.

## Project management

- [Status and validation scope](docs/status.md)
- [Contributing](CONTRIBUTING.md)
- [Issues](https://github.com/edoode/relay-probe-studio/issues)

Basic checks validates syntax only; relay behavior and macOS packaging require separate runtime checks.

## Why This Exists

Relay services often look OpenAI-compatible on the surface, but the details can be messy:

- `/models` may be incomplete or misleading
- a requested model ID may be silently remapped
- repeated calls may drift across backends
- a route may work once but fail under short burst testing

Relay Probe Studio gives you a clean local interface to check those behaviors before you rely on a relay in daily use.

## Features

- Test any model ID against an OpenAI-compatible relay
- Inspect `/models` metadata exposure
- Compare `requested_model` and `response_model`
- Measure repeated-request consistency
- Check JSON-format response behavior
- View a polished local web UI instead of raw terminal output
- Launch with a one-click Terminal script
- Build a macOS `.app` bundle for double-click usage

## What The App Tells You

- Whether a relay publicly lists the model you want
- Whether the model can actually be called
- Whether the returned `response_model` matches the model ID you requested
- Whether repeated requests stay stable at low temperature
- Whether the route looks reasonably trustworthy or suspicious

## Requirements

- macOS
- Python 3

## Quick Start

### Run with the Terminal launcher

```bash
cd /path/to/relay-probe-studio
./start.command
```

This starts the local web server and opens the UI in your browser.

### Build the macOS app bundle

```bash
cd /path/to/relay-probe-studio
./build_app.command
```

Then open `中转稳定性检测.app`.

If `图标.png` exists in the project root, the app bundle will use it as the custom icon.

## Privacy

- The UI runs locally on `127.0.0.1`
- The browser sends the API key to the local Python server; the server uses it in Authorization headers when calling the relay endpoint you configure
- The project does not upload your configuration anywhere on its own

## Limitations

- A relay can still lie about the true upstream model
- Matching metadata does not prove the upstream with absolute certainty
- This tool is best at finding inconsistency, remapping, instability, and missing metadata

## Project Structure

- `probe_web.py`: local web server and UI backend
- `relay_probe.py`: relay probing engine
- `web/`: frontend assets
- `start.command`: one-click Terminal launcher
- `build_app.command`: macOS app bundle builder
- `app_launcher.sh`: internal launcher used by the app bundle

## Typical Use Cases

- Check whether a relay really supports `gpt-5.4`
- Compare behavior across multiple advertised model IDs
- Verify whether a coding route is stable enough for daily use
- Sanity-check a newly purchased or newly configured relay endpoint

## Development

Run a quick syntax check:

```bash
python3 -m py_compile relay_probe.py probe_web.py
node --check web/app.js
```

## License

MIT
