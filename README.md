# WhatsApp Web Auto-Reply

Selenium automation for WhatsApp Web: reads messages in real time, generates replies with a local LLM (Ollama), and types them back into the chat.

## Features

- Connects via QR code (session persisted for repeat runs)
- Real-time message polling
- Auto-reply using Ollama (local LLM)
- Human-like typing (character-by-character)
- TEST_MODE for solo testing (reply to your own messages)

## Requirements

- Python 3.9+
- Chrome or Chromium
- [Ollama](https://ollama.com) with a model pulled (e.g. `ollama pull gemma3:1b`)

## Setup

```bash
python -m venv venv
venv\Scripts\Activate.ps1    # Windows
pip install -r requirements.txt
```

## Run

```bash
python whatsapp_reader.py
```

1. Scan the QR code (first time only).
2. Open a chat in the left panel (or let it open the first one).
3. Press Enter in the terminal to exit.

## Configuration

Edit the constants at the top of `whatsapp_reader.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `gemma3:1b` | Ollama model name (see `ollama list`) |
| `AUTO_REPLY` | `True` | Enable/disable auto-reply |
| `TEST_MODE` | `True` | Reply to your own messages (for testing alone) |
| `POLL_INTERVAL` | `3` | Seconds between message checks |

## Testing Alone (TEST_MODE)

1. Set `TEST_MODE = True`.
2. Open "Message yourself" or "Notes to self" in WhatsApp.
3. Send a message from your phone.
4. The script will reply via Ollama.

Set `TEST_MODE = False` for normal use (replies only to others).

## Troubleshooting

- **REPLY FAIL / Could not type** – Chat input not found. Ensure a chat is open and the compose box is visible.
- **REPLY SKIP / Ollama returned empty** – Ensure Ollama is running. Check model name with `ollama list`.
- **bind: Only one usage...** – Ollama is already running. No need to run `ollama serve` again.
- **QR every time** – Session is saved in `wa-chrome-profile`. Don't delete that folder.
