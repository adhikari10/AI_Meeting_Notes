# AI Meeting Note Taker

An intelligent meeting assistant with **two interfaces**: a **CLI backend** and a **Web Application**. Records audio, transcribes it in real-time using OpenAI Whisper, and generates automated meeting summaries, action items, and decisions using AI (Groq, DeepSeek, or OpenAI).

## Features

- 🎤 **Real-time Audio Capture** - Records from microphone or system audio (speaker output)
- 🗣️ **Live Transcription** - Uses OpenAI Whisper for accurate speech-to-text
- 🤖 **AI Analysis** - Automatically extracts:
  - Meeting summaries
  - Action items
  - Decisions made
  - Key insights
- 🌐 **Web Interface** - Beautiful, modern web UI for easy access
- 💻 **CLI Interface** - Terminal-based interface for power users
- 💾 **Data Storage** - Saves meetings and notes (SQLite for CLI, JSON for webapp)
- 📊 **Export Options** - Download notes as text files
- 🎨 **Rich UI** - Clean, professional interface for both CLI and web

## Project Structure

```
AI_note_taker/
├── .env                      # Environment variables (API keys)
├── .env.example              # Example environment file
├── .gitignore               # Git ignore rules
├── README.md                # This file
├── requirements.txt         # Python dependencies
│
├── backend/                 # CLI Backend Application
│   ├── api_client.py        # API client interface
│   ├── config.py            # Configuration management
│   ├── database.py          # Database operations
│   ├── main.py              # Main CLI entry point
│   ├── meeting_ai.py        # AI analysis logic
│   ├── meeting_assistant.py # Meeting assistant
│   ├── meeting_capture.py   # Audio capture logic
│   ├── meeting_notes/       # Saved CLI notes
│   ├── smart_notes.py       # Smart notes processing
│   ├── start.py             # Backend startup script
│   └── transcriber.py       # Transcription logic
│
├── meeting_notes_webapp/    # Web Application
│   ├── app.py              # Flask web server
│   ├── templates/          # HTML templates
│   │   └── index.html
│   ├── static/             # CSS/JS/assets
│   │   ├── css/
│   │   └── js/
│   ├── notes/              # Webapp saved notes
│   └── uploads/            # Uploaded audio files
│
└── venv/                    # Python virtual environment
```

## Requirements

- Python 3.8+
- Microphone or audio input device
- Groq API key (free) OR DeepSeek/OpenAI API key

## Installation & Launch (Windows)

### New user — one-time setup

1. **Install Python 3.10+** from [python.org](https://python.org) if you don't have it.

2. **Double-click `install.bat`**

   This will:
   - Create a `venv/` virtual environment
   - Install all dependencies from `requirements.txt`
   - Create a **"Meeting Notes AI"** shortcut on your Desktop

3. **Double-click the Desktop shortcut** (or `run_app.bat`) to launch.

4. On first launch, a setup page appears — enter your API key and you're done.
   The app opens in its own window (no browser needed).

> **Get a free Groq API key:** [console.groq.com/keys](https://console.groq.com/keys) — no credit card required.

---

### Files added for launching

| File | Purpose |
|---|---|
| `install.bat` | One-time setup — creates venv, installs deps, creates Desktop shortcut |
| `run_app.bat` | Daily launcher — finds Python in venv and starts the app |
| `create_shortcut.ps1` | PowerShell script called by `install.bat` to create the Desktop shortcut |
| `launcher.py` | Python entry point — starts Flask in background, opens pywebview window |

---

### Manual launch (developers)

```bash
# One-time
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Every launch
venv\Scripts\python.exe launcher.py
```

Or run the web server directly (browser-only, no desktop window):

```bash
cd meeting_notes_webapp
python app.py
# then open http://localhost:5000
```

---

### Changing your API key

Click **Settings** in the footer of the app at any time, or go to `http://localhost:5000/setup`.

---

### CLI Backend (power users)

```bash
cd backend
python main.py
```

**Workflow:**
1. Select audio device from the list
2. Start meeting — recording begins automatically
3. See live transcription and AI analysis in the terminal
4. Press `Ctrl+C` to stop and generate final report
5. Meeting notes saved to `backend/meeting_notes/`

## Output Files

### Web Application
- **`meeting_notes_webapp/notes/*.json`** - Saved meeting notes with full analysis
- **`meeting_notes_webapp/uploads/`** - Uploaded audio files

### CLI Backend
- **`backend/meetings.db`** - SQLite database with all meetings
- **`backend/meeting_notes/*.txt`** - Text reports of meetings

### Sample Report Structure

```json
{
  "title": "meeting_upload_20260203_172345.json",
  "timestamp": "2026-02-03T17:23:45.123456",
  "source": "upload",
  "file": "team_meeting.mp3",
  "transcript": "Full meeting transcript...",
  "summary": "Brief 1-2 sentence summary of the meeting",
  "actions": [
    "John: Fix database bug by Friday",
    "Sarah: Review PR #123"
  ],
  "decisions": [
    "Move to bi-weekly sprints",
    "Adopt new deployment process"
  ]
}
```

## Configuration Options

### Web Application
Configure in `meeting_notes_webapp/app.py`:
- **AI Model Selection** - Choose from Groq, DeepSeek, or local processing
- **Upload Limits** - Max 100MB file size
- **Audio Processing** - Whisper base model (configurable)

### CLI Backend
Edit `backend/config.py` to customize:
- **`SAMPLE_RATE`** - Audio sample rate (default: 16000 Hz)
- **`CHUNK_DURATION`** - Audio chunk size in seconds (default: 5)
- **`WHISPER_MODEL`** - Model size: tiny, base, small, medium, large
- **`DB_PATH`** - Database file location

## Troubleshooting

### PyAudio Installation Issues

**Windows:**
```bash
pip install pipwin
pipwin install pyaudio
```

**macOS:**
```bash
brew install portaudio
pip install pyaudio
```

**Linux:**
```bash
sudo apt-get install portaudio19-dev python3-pyaudio
pip install pyaudio
```

### Web Application Not Starting

1. Check if port 5000 is already in use
2. Verify all dependencies are installed: `pip install -r requirements.txt`
3. Check Flask and Flask-SocketIO are installed correctly
4. Review terminal output for specific error messages

### No Audio Detected

1. Check microphone permissions in system settings
2. Run `backend/start.py` to test microphone
3. Try selecting a different device
4. Ensure microphone is not muted
5. For speaker capture, enable "Stereo Mix" in Windows sound settings

### API Errors

- Verify API key is correct in `.env` file
- Check API rate limits and quota
- Ensure you have internet connection
- For Groq: Free tier has generous limits
- For DeepSeek: Check credit balance
- For OpenAI: Verify billing is set up

### Whisper Model Issues

- First run downloads the model (may take time)
- Try a smaller model if running out of memory
- Ensure sufficient disk space (~1-5GB for models)
- Check internet connection for initial download

## Dependencies

Core dependencies:
- **openai-whisper** - Speech-to-text transcription
- **pyaudio** - Audio capture
- **openai** - API client for Groq/DeepSeek/OpenAI
- **flask** - Web application framework
- **flask-socketio** - Real-time communication
- **flask-cors** - Cross-origin resource sharing
- **python-dotenv** - Environment variable management
- **rich** - Terminal UI (CLI only)
- **numpy** - Numerical operations

See `requirements.txt` for complete list.

## API Costs

**Groq (Recommended):**
- FREE tier with generous limits
- Fast inference (~400 tokens/sec)
- No credit card required

**DeepSeek:**
- Very affordable (~$0.14 per 1M input tokens)
- Good for high-volume usage

**OpenAI:**
- GPT-3.5-turbo: ~$0.50 per 1M input tokens
- Higher cost but widely available

**Whisper:**
- Runs locally, no API costs
- Uses CPU/GPU resources

## Privacy & Security

- ⚠️ **Never commit your `.env` file with API keys**
- `.env` is automatically excluded by `.gitignore`
- Audio is processed locally with Whisper
- Transcripts are sent to AI provider for analysis only
- All data stored locally in your machine
- No telemetry or tracking
- Review your AI provider's privacy policy

## Tips for Best Results

1. **Use a good microphone** - Better audio = better transcription
2. **Minimize background noise** - Improves accuracy significantly
3. **Speak clearly** - Helps Whisper transcribe correctly
4. **Test before important meetings** - Run `backend/start.py` first
5. **Choose appropriate Whisper model**:
   - `tiny` - Fastest, less accurate (good for testing)
   - `base` - Good balance (recommended)
   - `small` - Better accuracy, slower
   - `medium/large` - Best accuracy, requires more resources
6. **For virtual meetings** - Enable Stereo Mix to capture speaker output
7. **Review generated reports** - AI may miss context or make errors

## Development

### Running in Development Mode

**Web Application:**
```bash
cd meeting_notes_webapp
python app.py
```
Debug mode is enabled by default. The server will auto-reload on file changes.

**CLI Backend:**
```bash
cd backend
python main.py
```

### Project Technologies

- **Backend**: Python 3.8+
- **Web Framework**: Flask + Flask-SocketIO
- **AI Models**: Whisper (local), Groq/DeepSeek/OpenAI (API)
- **Database**: SQLite (CLI), JSON (webapp)
- **Frontend**: HTML, CSS, JavaScript (Vanilla)
- **Real-time**: WebSockets via Socket.IO

## Contributing

Contributions are welcome! To contribute:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Test thoroughly
5. Commit your changes: `git commit -m "Add feature"`
6. Push to the branch: `git push origin feature-name`
7. Submit a pull request

Please ensure your code follows Python best practices and includes appropriate documentation.

## Known Issues

- PyAudio can be tricky to install on some systems
- First Whisper model download may take several minutes
- WebSocket connections may drop on slow networks (will auto-reconnect)
- Large audio files (>100MB) may take time to process

## Roadmap

- [ ] Speaker diarization (identify who said what)
- [ ] Multi-language support
- [ ] Calendar integration
- [ ] Email summaries
- [ ] Mobile app
- [ ] Cloud deployment options
- [ ] Team collaboration features

## License

MIT License - Feel free to use and modify for your needs.

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Review error messages carefully
3. Ensure all dependencies are installed
4. Verify API keys are configured correctly
5. Check existing GitHub issues
6. Open a new issue with:
   - Clear description of the problem
   - Steps to reproduce
   - Error messages (if any)
   - Your environment (OS, Python version)

## Acknowledgments

- OpenAI Whisper for excellent speech recognition
- Groq for providing fast, free AI inference
- Flask community for the excellent web framework
- All contributors and users

---

**Happy Note Taking! 📝🤖**

Made with ❤️ by Bibek Adhikari
