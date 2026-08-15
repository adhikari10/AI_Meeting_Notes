# Smart Meeting Notes

Turn any meeting recording into a clean, structured set of notes. Upload an
audio or video file (or paste a link), and get back a full transcript plus an
AI-generated summary, key points, action items, decisions, open questions, and
next steps — in seconds.

> **Try it now:** (https://ai-meeting-notes-65ar.onrender.com/)
> No sign-up, nothing to install. Upload a file or paste a link and you're done.
> *(Free preview — see [Limits](#limits) below.)*

---

## What it does

- **Transcription** — accurate speech-to-text on your recordings.
- **Structured summary** — every transcript is distilled into six fields:
  summary, key points, action items, decisions, open questions, and next steps.
- **Chat with your transcript** — ask follow-up questions about what was said.
- **Speaker labels** — on uploaded files, speakers are separated (Speaker A,
  Speaker B, …) where the audio supports it.
- **Export** — download your notes as a text file.

There are two ways to use it: the **hosted preview** (easiest), or **run it
yourself** for full local processing and live recording.

---

## Option 1 — Hosted preview

The fastest way to try it. Nothing to install.

1. Go to **https://ai-meeting-notes-65ar.onrender.com/**
2. Either:
   - **Upload** an audio or video file, or
   - **Paste a link** to a media file.
3. Wait a few seconds for transcription and analysis.
4. Read your notes across the tabs (Transcript, Summary, Actions), chat with
   the transcript, or download the result.

### Limits

The hosted version is a free preview, so a few things are intentionally capped:

- **Upload-only.** Live recording isn't available in the hosted version — that
  lives in the self-hosted edition (below).
- **File size** is limited (currently around 50 MB per upload).
- **Daily usage** is limited per user to keep the preview free for everyone.
- **Direct media links work best.** Links to hostile platforms (e.g. YouTube,
  TikTok) may not download in the hosted version — use a direct file link or
  upload the file instead.
- **Nothing is stored on the server.** The hosted preview is stateless: your
  transcript and notes live in your browser session and are not saved
  server-side. Close the tab and they're gone.

---

## Option 2 — Run it yourself (self-hosted)

The self-hosted edition is the full-featured version: it transcribes locally
with Whisper, supports **live recording** (capture a meeting as it happens), and
saves your notes to disk. You bring your own API key for the AI summary step.

### Requirements

- **Python 3.11** (3.9+ should work; 3.11 is what's tested)
- **ffmpeg** on your system PATH (used to decode audio/video)
- A **Groq API key** (free tier is generous) — or another supported provider
- Windows, macOS, or Linux

> **Note on live recording:** capturing system/speaker audio is best supported
> on Windows. On macOS/Linux you can still record from a microphone and process
> uploaded files.

### 1. Clone and enter the project

```bash
git clone https://github.com/adhikari10/AI_Meeting_Notes/
cd AI_note_taker
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

Dependencies are split into layers so you only install what you need.

**For the full desktop experience (local Whisper + live recording):**
```bash
pip install -r requirements-base.txt
pip install -r requirements-desktop.txt
```

**If you only want the web/upload features (no local recording):**
```bash
pip install -r requirements-web.txt
```

> **ffmpeg:** if you don't already have it —
> Windows: `choco install ffmpeg` (or download from ffmpeg.org and add to PATH).
> macOS: `brew install ffmpeg`.
> Linux: `sudo apt-get install ffmpeg`.

> **PyAudio on Windows:** if `pip` fails to build it, try
> `pip install pipwin && pipwin install pyaudio`.

### 4. Add your API key

Copy the example env file and fill in your key:

```bash
cp .env.example .env
```

Then open `.env` in a text editor and set at least:

```
GROQ_API_KEY=your-groq-api-key-here
```

Get a free Groq key at <https://console.groq.com>. Other providers (OpenAI,
DeepSeek) are supported via their own keys — see `.env.example` for the options.

> ⚠️ **Never commit `.env`.** It's already in `.gitignore`. Only `.env.example`
> (with no real keys) belongs in the repo.

> **Edit `.env` in a real editor**, not by appending from PowerShell — the `>>`
> operator writes the wrong encoding and can corrupt the file.

### 5. Run

```bash
cd meeting_notes_webapp
python app.py
```

Then open **http://localhost:5000** in your browser.

---

## Using the app

The interface has a sidebar with a few views:

- **Record** *(self-hosted only)* — capture a live meeting. Pick an audio
  device and start; transcription appears as the meeting goes. On Windows you
  can capture speaker output (for Zoom/Teams/Meet) by enabling **Stereo Mix**
  in your sound settings.
- **Upload** — drop in an audio/video file, or paste a media link. Watch it
  transcribe and analyze, then review the results.
- **My Notes** *(self-hosted only)* — your saved notes, stored as JSON files on
  disk. Open any note to view its transcript, summary, and actions, or download
  it.
- **Recap** — a consolidated view of the generated summary and highlights.

Supported upload formats include common audio and video types (MP3, WAV, M4A,
MP4, and similar). Larger or noisier recordings take longer and transcribe less
cleanly — good input audio is the single biggest factor in output quality.

---

## How it works

1. **Audio in** — from an uploaded file, a pasted link, or (self-hosted) a live
   recording.
2. **Transcription** — Groq's hosted Whisper, or a local Whisper model on the
   desktop edition, converts speech to text. Uploaded files can additionally be
   run through a diarization step to separate speakers.
3. **Analysis** — the transcript is sent to an LLM (Llama 3.3 via Groq by
   default) which returns the six structured fields.
4. **Output** — results are shown in the browser and, on the self-hosted
   edition, saved to disk as JSON.

---

## Configuration

Set these in your `.env` (self-hosted) — see `.env.example` for the full list:

| Variable          | Purpose                                            |
|-------------------|----------------------------------------------------|
| `GROQ_API_KEY`    | Powers transcription (hosted Whisper) and summary. |
| `OPENAI_API_KEY`  | Optional alternative AI provider.                  |
| `DEEPSEEK_API_KEY`| Optional alternative AI provider.                  |
| `WHISPER_MODEL`   | Local Whisper size: `tiny`/`base`/`small`/`medium`/`large`. `base` is a good default. |

If no AI key is set, the app falls back to a basic non-AI summary so it still
runs — but the quality is much lower. A Groq key is strongly recommended.

---

## Troubleshooting

**App won't start / port in use**
Something else is on port 5000. Stop it, or change the port in `app.py`.

**"Module not found"**
Your virtual environment isn't active, or dependencies aren't installed for the
edition you're running. Re-activate the venv and re-run the relevant
`pip install -r ...` from step 3.

**Transcription or summary fails**
Check that `GROQ_API_KEY` is set correctly in `.env`, that the key is valid, and
that you have an internet connection. Try a smaller file.

**A pasted link fails to download**
Direct media links work best. Some platforms actively block automated
downloads; upload the file directly instead.

**No audio captured (live recording)**
Confirm the right input device is selected and not muted. For speaker capture on
Windows, enable **Stereo Mix** in your sound settings.

**Whisper is slow or runs out of memory (self-hosted)**
Use a smaller `WHISPER_MODEL` (e.g. `base` or `tiny`). The first run downloads
the model, which can take a while.

---

## Privacy

- **Hosted preview:** stateless. Transcripts and notes are not saved on the
  server — they exist only in your browser session.
- **Self-hosted:** everything stays on your machine. Audio is transcribed
  locally (with local Whisper), notes are saved to your own disk, and the only
  data that leaves your computer is the transcript text sent to your chosen AI
  provider for the summary step. Review that provider's privacy policy.
- **Never commit your `.env`** — it holds your API keys and is gitignored by
  default.

---

## License

<LICENSE_PLACEHOLDER — add your license, e.g. MIT>
