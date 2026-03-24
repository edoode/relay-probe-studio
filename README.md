# Relay Probe Studio

Apple-style local UI for checking whether an OpenAI-compatible relay really supports a target model and how stable that route is.

## What It Does

- Tests a relay with a model ID you choose
- Checks `/models` metadata exposure
- Verifies whether `response_model` matches the requested model
- Measures consistency under repeated requests
- Provides a polished local web UI
- Can be wrapped as a macOS `.app`

## Files

- `probe_web.py`: local web server
- `relay_probe.py`: relay probing engine
- `web/`: UI assets
- `start.command`: one-click Terminal launcher
- `build_app.command`: build the macOS app bundle
- `app_launcher.sh`: internal launcher used by the app bundle

## Quick Start

### Run in Terminal

```bash
cd /path/to/project
./start.command
```

### Run as macOS App

```bash
cd /path/to/project
./build_app.command
```

Then open `中转稳定性检测.app`.

## Requirements

- macOS
- Python 3

## Notes

- The UI runs locally on `127.0.0.1`
- API keys are sent only to the local server process
- This project does not prove the true upstream model with absolute certainty if a relay lies
