# Android Social Uploader

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-9%20passing-brightgreen.svg)](tests/)

An automated **Android UI automation framework** that uploads videos to social
platforms (TikTok, Instagram, YouTube Studio) powered by **vision-based LLMs**.
Instead of relying on brittle, hardcoded coordinates, the framework takes a
screenshot of the device, feeds it to a multimodal LLM together with the parsed
accessibility tree, and lets the model decide the next UI action.

## ✨ Features

- **Vision-based AI Agent** — Uses LLMs (Google Gemini, NVIDIA NIM, Cerebras) to analyze screenshots and decide the next UI action.
- **Zero-cost pipeline** — Defaults to NVIDIA NIM's free tier so the whole automation loop can run without paying for inference.
- **Hybrid perception** — Combines screenshots with the parsed UIAutomator accessibility tree for robust element detection.
- **Multi-platform uploads** — Automates TikTok, Instagram and YouTube Studio upload flows.
- **Provider abstraction** — A single `BaseLLMProvider` interface with pluggable backends.
- **Self-correcting clicks** — The agent can perform intermediate corrective actions (click, swipe, press key, wait) to reach the target element.
- **Automatic documentation** — Generates a Markdown guide of every executed step.
- **Debug mode** — Optional annotated screenshots and verbose logging (off by default).
- **Screen recording** — Optional screen recording during test execution.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       job_runner.py                         │
│              (entry point · job polling loop)               │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                      job_processor.py                       │
│        (download · push to device · orchestrate uploads)    │
└──────────────────────────────┬──────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  platforms/   │    │  platforms/   │    │  platforms/   │
│   tiktok.py   │    │ instagram.py  │    │  youtube.py   │
└───────┬───────┘    └───────┬───────┘    └───────┬───────┘
        └────────────────────┼────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      ui_automator.py                        │
│   (ADB helpers · vision-based agent_click · text input)     │
└─────────────────────────────────────────────────────────────┘
```

### Module layout

```
auto-test-android/
├── job_runner.py        # Entry point for job processing (polling mode)
├── job_processor.py     # Download / push / upload orchestration
├── ui_automator.py      # Shared ADB + vision-based agent click helpers
├── adb_controller.py    # ADB device control wrapper
├── llm_provider.py      # LLM provider abstractions (Gemini, NIM, Cerebras)
├── step_recorder.py     # Action recording & markdown guide generation
├── config.py            # Centralized configuration (DEBUG flag, API keys)
├── platforms/           # Per-platform upload automations
│   ├── base.py          #   BaseUploader abstract class
│   ├── tiktok.py        #   TikTok upload flow
│   ├── instagram.py     #   Instagram upload flow
│   └── youtube.py       #   YouTube Studio upload flow
├── requirements.txt     # Python dependencies
├── pytest.ini           # Pytest configuration
├── tests/               # Unit tests
└── docs/                # Generated guides
```

## 📋 Prerequisites

- Python 3.10+
- Android device with USB debugging enabled
- ADB installed and in `PATH`
- An API key for at least one LLM provider:
  - **Google Gemini** — [Get API Key](https://makersuite.google.com/app/apikey)
  - **NVIDIA NIM** — [Get API Key](https://build.nvidia.com/explore/discover)
  - **Cerebras** — [Get API Key](https://cloud.cerebras.ai/)

## 💸 Zero-cost pipeline with NVIDIA NIM

The framework is designed to run as a **zero-cost pipeline** by defaulting to
**NVIDIA NIM** as the vision provider. NVIDIA NIM offers free API access to a
set of hosted models (including vision-capable ones), which makes it possible
to run the whole automation loop — screenshots, accessibility-tree parsing and
UI decisions — **without paying for inference**.

> **Why NVIDIA NIM?** The provider selection in `init_agent_llm()` prioritizes
> NVIDIA NIM because it provides a free tier, whereas Google Gemini and Cerebras
> are typically metered/paid. This lets you experiment and run the framework at
> no cost.

### ⚠️ Understanding the NVIDIA NIM terms of service

Using the free tier comes with constraints you should be aware of before
relying on it in production:

- **Rate limits** — Free API keys are subject to request-rate and
  concurrency limits. Long automation runs that issue many LLM calls per click
  loop can hit these limits, causing throttling or temporary failures.
- **Model availability** — The set of free models (and their versions) can
  change over time. A model name that works today may be deprecated or
  replaced, so pin the model you depend on and re-check periodically.
- **Non-commercial / evaluation intent** — The free tier is intended for
  evaluation and development. Review the current
  [NVIDIA NIM terms](https://build.nvidia.com/) to confirm whether your use
  case (e.g. commercial automation) is permitted.
- **Data handling** — Free endpoints may process prompts (including the
  screenshots you send) under different data-retention terms than paid plans.
  Do not send sensitive or personal data if that is a concern.
- **No SLA** — The free tier has no uptime or performance guarantee. For
  reliable, high-volume automation, plan for a paid plan or a fallback
  provider.

> **Recommendation:** treat NVIDIA NIM as the **default, zero-cost option for
> development and demos**. For production workloads, configure a paid provider
> (Gemini or Cerebras) via `.env` and set `--provider` accordingly.

## 🚀 Installation

```bash
# Clone the repository
git clone <repository-url>
cd auto-test-android

# Create a virtual environment
python -m venv venv
source venv/bin/activate        # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy the environment template and add your API keys
cp .env.example .env
# Edit .env with your actual API keys
```

## ⚙️ Configuration

Create a `.env` file from the template:

```bash
cp .env.example .env
```

Edit `.env` with your configuration:

```env
# Required: at least one API key
GOOGLE_API_KEY=your_google_api_key
NVIDIA_NIM_API_KEY=your_nvidia_nim_api_key
CEREBRAS_API_KEY=your_cerebras_api_key

# Optional: NVIDIA NIM base URL
NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1

# Optional: Device ID (leave empty if only one device)
DEVICE_ID=

# Optional: backend API URL for job polling (job_runner.py only)
API_URL=http://your-vps-address:port

# Optional: enable debug mode (verbose logging + annotated screenshots)
DEBUG=false

# Optional: polling interval in seconds
POLL_INTERVAL=15

# Optional: local download directory
LOCAL_DOWNLOAD_DIR=./downloads

# Optional: max agent attempts per click
MAX_AGENT_ATTEMPTS=10
```

> **Security note:** API keys are never hardcoded. They are read from environment
> variables via `config.py`. The `.env` file is gitignored and never committed.

## 🎮 Usage

### Job processing mode (`job_runner.py`)

Processes jobs from a backend API (polls for jobs, downloads media, automates uploads):

```bash
# Run with a specific job ID
python job_runner.py --job-id 84

# Run in continuous polling mode
python job_runner.py
```

## 🐛 Debug mode

Debug mode is **off by default** to keep the working tree clean during normal
runs. When enabled, it produces verbose logging, annotated screenshots and the
generated upload guides.

Enable it with the `--debug` flag:

```bash
# Run a single job with debug artifacts
python job_runner.py --job-id 84 --debug
```

Or via the `DEBUG` environment variable / `.env` file:

```bash
DEBUG=true python job_runner.py --job-id 84
```

When enabled:

- Verbose logging is shown (via the `logging` module).
- Screenshots with click markers are saved to `./debug_agent_clicks/`.
  - **Green** circles = successful clicks.
  - **Yellow** circles = intermediate corrective actions.
  - **Red** circles = fallback clicks.
- The upload guide is generated in `docs/guida_caricamento_*.md`.

When disabled (default), none of these artifacts are produced.

## 🧪 Running tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run a specific test file
pytest tests/test_platforms.py
```

## 📄 License

This project is licensed under the [MIT License](LICENSE).
