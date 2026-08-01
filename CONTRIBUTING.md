# Contributing to AntiSmurf

Thank you for your interest in contributing. This project is open source and welcomes bug reports, documentation improvements, and pull requests.

## Before you start

- Read [README.md](README.md) for setup and usage
- Check existing [Issues](https://github.com/STCrazyCat/KerriganSurvival2Antismurf/issues) to avoid duplicate work
- For large features, open an issue first to discuss design

## Development setup

**Python 3.11–3.13 (64-bit) required.** PaddlePaddle does not provide wheels for Python 3.14 yet.

```bash
git clone https://github.com/STCrazyCat/KerriganSurvival2Antismurf.git
cd AntiSmurf
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
.\scripts\install_vision_deps.ps1
pip install pytest
python -m pytest
```

CI uses [requirements-ci.txt](requirements-ci.txt) (no PaddleOCR download) for faster automated tests. Install the full `requirements.txt` when working on vision/OCR features.

## Code guidelines

- Match existing style in surrounding modules
- Keep changes focused; avoid unrelated refactors
- Add or update tests for behavior changes
- Do not commit secrets (`config/user.toml`, API keys)
- Do not commit user databases under `data/` or local replay binaries

## Pull request checklist

- [ ] `python -m pytest` passes locally
- [ ] README or docs updated if user-facing behavior changed
- [ ] `CHANGELOG.md` updated under `[Unreleased]` for notable changes
- [ ] No secrets or personal paths committed

## Reporting bugs

Use the [Bug report](https://github.com/STCrazyCat/KerriganSurvival2Antismurf/issues/new?template=bug_report.md) template and include:

- Windows version and AntiSmurf version (`VERSION` file or About if shown)
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs from `logs/` (redact handles if needed)

## Release maintainers

See [docs/RELEASING.md](docs/RELEASING.md).
