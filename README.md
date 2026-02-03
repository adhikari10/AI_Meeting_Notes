# AI Meeting Note Taker

An intelligent meeting assistant that records audio, transcribes it in real-time using OpenAI Whisper, and generates automated meeting summaries, action items, and decisions using AI (DeepSeek or OpenAI).

## Features

- 🎤 **Real-time Audio Capture** - Records from your microphone or system audio
- 🗣️ **Live Transcription** - Uses OpenAI Whisper for accurate speech-to-text
- 🤖 **AI Analysis** - Automatically extracts:
  - Meeting summaries
  - Action items
  - Decisions made
  - Questions raised
- 💾 **Database Storage** - Saves meetings and notes to SQLite database
- 📊 **Final Reports** - Generates comprehensive meeting reports in JSON format
- 🎨 **Rich Terminal UI** - Beautiful live dashboard using Rich library

## Requirements

- Python 3.8+
- Microphone or audio input device
- DeepSeek or OpenAI API key

## Installation

### 1. Clone or Download the Project

```bash
cd AI_note_taker
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

### 3. Activate Virtual Environment

**Windows:**
```bash
venv\Scripts\activate
```

**macOS/Linux:**
```bash
source venv/bin/activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

**Note:** Installing PyAudio on Windows may require additional steps:
- Download the appropriate `.whl` file from [here](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio)
- Install with: `pip install PyAudio-0.2.11-cpXX-cpXXm-win_amd64.whl`

### 5. Configure Environment Variables

Create a `.env` file in the project root:

```env
# Choose ONE provider:
# Option A: DeepSeek
DEEPSEEK_API_KEY=your-deepseek-api-key-here
AI_PROVIDER=deepseek
AI_MODEL=deepseek-chat

# Option B: OpenAI
# OPENAI_API_KEY=your-openai-api-key-here
# AI_PROVIDER=openai
# AI_MODEL=gpt-3.5-turbo

# Whisper Model (tiny, base, small, medium, large)
WHISPER_MODEL=base
```

**Get API Keys:**
- DeepSeek: [https://platform.deepseek.com](https://platform.deepseek.com)
- OpenAI: [https://platform.openai.com](https://platform.openai.com)

## Usage

### Run the Meeting Assistant

```bash
python main.py
```

### Workflow

1. **Select Audio Device** - Choose your microphone from the list
2. **Start Meeting** - Recording begins automatically
3. **Live Analysis** - See real-time transcription and AI analysis
4. **End Meeting** - Press `Ctrl+C` to stop
5. **Final Report** - Automatically generates and saves meeting report

### Test Your Microphone

```bash
python start.py
```

This will record for 3 seconds and verify your microphone is working.

## Project Structure

```
AI_note_taker/
├── main.py              # Main application entry point
├── audio_capture.py     # Audio recording functionality
├── transcriber.py       # Whisper transcription
├── meeting_ai.py        # AI analysis logic
├── api_client.py        # DeepSeek/OpenAI API client
├── database.py          # SQLite database operations
├── config.py            # Configuration management
├── start.py             # Microphone test utility
├── requirements.txt     # Python dependencies
├── .env                 # Environment variables (create this)
├── meetings.db          # SQLite database (auto-created)
└── meeting_report_*.json # Generated reports
```

## Output Files

- **`meetings.db`** - SQLite database with all meetings and live notes
- **`meeting_report_YYYYMMDD_HHMM.json`** - Final meeting reports

### Sample Report Structure

```json
{
  "title": "Team Standup Meeting",
  "executive_summary": "Quick team sync covering progress updates...",
  "key_points": [
    "Sprint progress review",
    "Blocker discussions"
  ],
  "action_items": [
    "John: Fix database bug by Friday",
    "Sarah: Review PR #123"
  ],
  "decisions": [
    "Move to bi-weekly sprints"
  ],
  "next_steps": [
    "Schedule architecture review",
    "Update project documentation"
  ],
  "participants": ["John", "Sarah", "Mike"],
  "duration_minutes": 15
}
```

## Configuration Options

Edit [config.py](config.py) to customize:

- **`SAMPLE_RATE`** - Audio sample rate (default: 16000 Hz)
- **`CHUNK_DURATION`** - Audio chunk size in seconds (default: 5)
- **`WHISPER_MODEL`** - Model size: tiny, base, small, medium, large
  - `tiny` - Fastest, less accurate
  - `base` - Good balance (recommended)
  - `large` - Most accurate, slower
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

### No Audio Detected

1. Check microphone permissions in system settings
2. Run `python start.py` to test microphone
3. Try selecting a different device when starting the app
4. Ensure microphone is not muted

### API Errors

- Verify API key is correct in `.env` file
- Check API rate limits and quota
- Ensure you have internet connection

### Whisper Model Issues

- First run downloads the model (may take time)
- Try a smaller model if running out of memory
- Ensure sufficient disk space for model files

## Dependencies

- **openai-whisper** - Speech-to-text transcription
- **faster-whisper** - Optimized Whisper implementation
- **pyaudio** - Audio capture
- **soundcard** - Alternative audio capture
- **openai** - OpenAI/DeepSeek API client
- **python-dotenv** - Environment variable management
- **rich** - Terminal UI
- **numpy** - Numerical operations
- **torch** - Deep learning framework (for Whisper)

## API Costs

**DeepSeek:**
- Very affordable (~$0.14 per 1M input tokens)
- Recommended for cost-effective operation

**OpenAI:**
- GPT-3.5-turbo: ~$0.50 per 1M input tokens
- Higher cost but widely available

**Whisper:**
- Runs locally, no API costs
- Uses CPU/GPU resources

## Privacy & Security

- ⚠️ **Never commit your `.env` file with API keys**
- Audio is processed locally with Whisper
- Transcripts are sent to AI provider for analysis
- Database is stored locally
- Review your AI provider's privacy policy

## Tips for Best Results

1. **Use a good microphone** - Better audio = better transcription
2. **Minimize background noise** - Improves accuracy
3. **Speak clearly** - Helps Whisper transcribe correctly
4. **Test before important meetings** - Run `start.py` first
5. **Choose appropriate Whisper model** - Balance speed vs accuracy
6. **Review generated reports** - AI may miss context

## Contributing

Feel free to submit issues, fork the repository, and create pull requests for any improvements.

## License

MIT License - Feel free to use and modify for your needs.

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Review error messages carefully
3. Ensure all dependencies are installed
4. Verify API keys are configured correctly

---

**Happy Note Taking! 📝🤖**
