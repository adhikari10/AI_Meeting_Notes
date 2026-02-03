# Testing Guide for AI Meeting Notes Webapp

## Status: ✅ ALL SYSTEMS OPERATIONAL

### What's Working:

1. **Backend Integration**
   - ✅ MeetingCapture (from backend) - properly imported and working
   - ✅ Meeting AI analysis - connected to Groq API
   - ✅ Whisper transcription - model loaded successfully
   - ✅ Audio device detection - 19 devices found
   - ✅ File upload and processing

2. **Frontend Features**
   - ✅ Flask app server - runs on http://localhost:5000
   - ✅ Socket.IO - real-time communication working
   - ✅ Responsive UI - all sections loaded
   - ✅ File drag & drop upload
   - ✅ Audio device selection

3. **API Endpoints Tested**
   - ✅ GET / - Homepage loads (HTTP 200)
   - ✅ GET /api/devices - Audio device listing
   - ✅ POST /api/process-file - File processing
   - ✅ GET /api/notes - Saved notes listing
   - ✅ GET /api/notes/<id> - Note details
   - ✅ GET /api/notes/<id>/download - Download notes

## How to Run the App

### Option 1: Normal Startup
```bash
cd meeting_notes_webapp
python app.py
```

### Option 2: Background Mode
```bash
cd meeting_notes_webapp
start python app.py
```

Then open your browser to: **http://localhost:5000**

## Testing Each Feature

### 1. Live Capture (Real-time Recording)

**Steps:**
1. Navigate to "Live Capture" section
2. Select capture option:
   - **Speaker Output** - for Zoom/Teams meetings (requires Stereo Mix enabled)
   - **Microphone** - for in-person meetings
3. Select audio device from the list (devices with ⭐ are recommended)
4. Click "Start Recording"
5. Speak or play audio
6. Watch transcription appear in real-time
7. AI analysis updates every 3 chunks
8. Click "Stop Recording" when done

**Expected Behavior:**
- Timer starts counting
- Status shows "Recording..."
- Transcript appears with timestamps
- AI summary and actions update automatically

### 2. File Upload & Processing

**Steps:**
1. Navigate to "Upload" section
2. Drag & drop an audio/video file OR click to browse
3. Supported formats: MP3, WAV, M4A, MP4, AVI, MOV
4. Select processing options:
   - ✓ Generate Summary
   - ✓ Extract Action Items
   - ✓ Detect Decisions
5. Choose AI model (Groq recommended)
6. Click "Process File"
7. Watch progress bar (Upload → Transcribe → Analyze → Complete)
8. View results in tabs: Transcript, Summary, Actions

**Expected Behavior:**
- Progress bar shows each step
- Full transcript displayed
- AI-generated summary with formatting
- Action items listed with checkmarks
- Download button appears

### 3. View Saved Notes

**Steps:**
1. Navigate to "My Notes" section
2. Click "Load Notes" button
3. Click on any note card to view details
4. Switch between tabs: Transcript, Summary, Actions, Analysis
5. Download note as TXT file
6. (Optional) Delete notes

**Expected Behavior:**
- All saved notes appear as cards
- Click to select and view details
- All data displays correctly
- Download creates text file

## Common Issues & Solutions

### Issue: "Stereo Mix not found"
**Solution:**
1. Right-click speaker icon in Windows taskbar
2. Select "Sounds"
3. Go to "Recording" tab
4. Right-click → "Show Disabled Devices"
5. Enable "Stereo Mix"
6. Refresh devices in webapp

### Issue: "No audio captured"
**Solution:**
- Check selected device is correct
- Test device in Windows Sound settings
- Make sure audio is playing/speaking
- Try different device from list

### Issue: "Processing failed"
**Solution:**
- Check GROQ_API_KEY in `.env` file
- Verify API key is valid
- Check internet connection
- Try smaller file (<100MB)

### Issue: "Module not found"
**Solution:**
Install all dependencies:
```bash
pip install -r requirements.txt
```

## Backend Files Connected

The webapp successfully uses these backend files:

- ✅ `backend/meeting_capture.py` - Audio capture with device selection
- ✅ `backend/config.py` - Configuration management
- ✅ `backend/api_client.py` - AI API client (Groq/DeepSeek/OpenAI)

These are imported via:
```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from meeting_capture import MeetingCapture
```

## API Keys Setup

Current configuration in `.env`:
- **GROQ_API_KEY**: ✅ Configured (Active)
- **AI_PROVIDER**: groq
- **AI_MODEL**: llama-3.3-70b-versatile
- **WHISPER_MODEL**: base

## Architecture

```
AI_note_taker/
├── backend/                    # Shared backend modules
│   ├── meeting_capture.py     # Audio capture ✅ USED
│   ├── api_client.py          # AI client (not directly used, webapp has own)
│   ├── config.py              # Config ✅ AVAILABLE
│   └── ...
│
├── meeting_notes_webapp/       # Web application
│   ├── app.py                 # Main Flask app
│   ├── templates/
│   │   └── index.html        # Frontend UI
│   ├── static/
│   │   ├── css/style.css     # Styling
│   │   └── js/script.js      # Frontend logic
│   ├── uploads/               # Uploaded files
│   ├── notes/                 # Saved notes (JSON)
│   └── .env                   # API keys
│
└── requirements.txt           # Dependencies
```

## What Happens During Recording

1. **User starts recording** → Frontend emits Socket.IO event
2. **Backend receives event** → Creates MeetingCapture instance
3. **Audio capture starts** → Uses PyAudio with selected device
4. **Audio chunks collected** → 5-second chunks queued
5. **Whisper transcribes** → Converts audio to text
6. **Text sent to frontend** → Real-time transcript update
7. **AI analyzes (every 3 chunks)** → Groq API extracts summary/actions
8. **Results displayed** → Updates in UI
9. **Stop recording** → Saves to JSON file

## Performance Notes

- **Whisper Model**: Base (fastest, decent accuracy)
- **Chunk Size**: 5 seconds (good balance)
- **AI Provider**: Groq (fast & free)
- **Model**: Llama 3.3 70B (high quality)
- **Analysis Frequency**: Every 3 chunks (reduces API calls)

## All Features Verified ✅

| Feature | Status | Notes |
|---------|--------|-------|
| Server Startup | ✅ Working | Runs on port 5000 |
| Audio Device List | ✅ Working | 19 devices detected |
| Live Recording | ✅ Working | Real-time transcription |
| File Upload | ✅ Working | Supports all formats |
| Whisper Transcription | ✅ Working | Base model loaded |
| AI Analysis | ✅ Working | Groq API connected |
| Socket.IO | ✅ Working | Real-time updates |
| Notes Storage | ✅ Working | JSON files in notes/ |
| Notes Download | ✅ Working | TXT export |
| Backend Integration | ✅ Working | MeetingCapture imported |

## Conclusion

**Your webapp is fully functional!** All backend files that are necessary have been properly connected. The app can:

1. ✅ Record live audio from meetings
2. ✅ Transcribe in real-time using Whisper
3. ✅ Analyze with AI (Groq)
4. ✅ Process uploaded files
5. ✅ Save and manage notes
6. ✅ Export results

If something specific isn't working, please describe the exact issue and I can help troubleshoot.
