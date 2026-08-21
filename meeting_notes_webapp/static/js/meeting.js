// meeting.js — all meeting-page logic
// Derived from script.js with two changes:
//   1. setupNavigation() targets only hash (#) links so global nav is unaffected
//   2. DOMContentLoaded switches to 'capture' (no 'home' section on meeting page)

let socket;
let isRecording = false;
let isPaused = false;
let timerInterval;
let startTime;
let elapsedTime = 0;
let selectedFile = null;
let selectedNote = null;
let chatHistory = [];
let currentChatNoteId = null;

document.addEventListener('DOMContentLoaded', function() {
    if (window.STANDALONE_NOTE_ID) {
        // Standalone /notes/<id> page — just load that one note, skip all
        // the recording-page setup (no capture UI, notes grid, etc. here).
        selectedNote = window.STANDALONE_NOTE_ID;
        loadNoteDetails(window.STANDALONE_NOTE_ID);
        return;
    }

    socket = io();
    setupNavigation();
    setupFileUpload();
    if (!window.CLOUD_MODE) {
        loadAudioDevices();
    }
    setupSocketEvents();
    // Cloud mode has no Live Capture / My Notes sections (see meeting.html),
    // so default straight to Upload there instead of the now-absent Capture.
    switchSection(window.CLOUD_MODE ? 'upload' : 'capture');
});

function setupNavigation() {
    // Sidebar nav items (data-view) — leaves footer/settings links alone
    const navItems = document.querySelectorAll('.nav-item[data-view]');
    navItems.forEach(item => {
        item.addEventListener('click', function() {
            const target = this.dataset.view;
            switchSection(target);

            navItems.forEach(n => n.classList.remove('active'));
            this.classList.add('active');

            if (target === 'notes') {
                loadNotes();
            }
        });
    });
}

function switchSection(sectionId) {
    document.querySelectorAll('.section').forEach(section => {
        section.classList.remove('active');
    });

    document.getElementById(sectionId).classList.add('active');
    window.location.hash = sectionId;

    if (sectionId === 'notes') {
        loadNotes();
    }
}

function selectOption(option, evt) {
    const cards = document.querySelectorAll('.option-card');
    cards.forEach(card => card.classList.remove('selected'));
    const e = evt || window.event;
    if (e && e.currentTarget) {
        e.currentTarget.classList.add('selected');
    }
    document.querySelector(`#${option}`).checked = true;
}

async function loadAudioDevices() {
    try {
        const response = await fetch('/api/devices');
        const devices = await response.json();

        const deviceList = document.getElementById('deviceList');
        deviceList.innerHTML = '<option value="" disabled selected>Select a device…</option>';

        devices.forEach((device, index) => {
            const option = document.createElement('option');
            option.value = index;
            option.textContent = `${device.name} (Inputs: ${device.inputs} | ${device.rate}Hz)`;
            deviceList.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading devices:', error);
    }
}

function startRecording() {
    if (window.CLOUD_MODE) {
        alert('Live recording is not available in cloud mode. Use Upload or paste a video URL instead.');
        return;
    }

    const selectedOption = document.querySelector('input[name="captureOption"]:checked');
    if (!selectedOption) {
        alert('Please select a capture option first!');
        return;
    }

    const deviceList = document.getElementById('deviceList');
    if (!deviceList.value) {
        alert('Please select an audio device!');
        return;
    }

    const captureType = selectedOption.value;
    const deviceId = parseInt(deviceList.value, 10);

    socket.emit('start_recording', {
        type: captureType,
        deviceId: deviceId
    });

    isRecording = true;
    document.getElementById('startBtn').disabled = true;
    document.getElementById('stopBtn').disabled = false;
    document.getElementById('pauseBtn').disabled = false;

    startTimer();

    const statusDot = document.querySelector('.status-dot');
    statusDot.classList.add('recording');
    document.querySelector('#statusIndicator span').textContent = 'Recording...';

    document.getElementById('transcript').innerHTML = '<div class="placeholder">Transcript will appear here...</div>';
    document.getElementById('analysis').innerHTML = '<div class="placeholder">Recording... Click Stop to generate summary</div>';
}

function stopRecording() {
    socket.emit('stop_recording');

    isRecording = false;
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
    document.getElementById('pauseBtn').disabled = true;

    stopTimer();

    const statusDot = document.querySelector('.status-dot');
    statusDot.classList.remove('recording', 'paused');
    document.querySelector('#statusIndicator span').textContent = 'Recording stopped';
}

function resetCapture() {
    if (isRecording) {
        stopRecording();
    }

    socket.emit('reset_transcript');

    document.getElementById('transcript').innerHTML = '<div class="placeholder">Transcript will appear here...</div>';
    document.getElementById('analysis').innerHTML = '<div class="placeholder">AI insights will appear here...</div>';

    stopTimer();
    elapsedTime = 0;
    document.getElementById('timer').textContent = '00:00:00';

    const statusDot = document.querySelector('.status-dot');
    statusDot.classList.remove('recording', 'paused');
    document.querySelector('#statusIndicator span').textContent = 'Ready to record';

    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
    document.getElementById('pauseBtn').disabled = true;
    isPaused = false;
    document.getElementById('pauseBtn').innerHTML = '<i class="fas fa-pause"></i> Pause';

    console.log('✅ Capture reset complete');
}

function togglePause() {
    if (!isRecording) return;

    isPaused = !isPaused;

    if (isPaused) {
        socket.emit('pause_recording');
        document.getElementById('pauseBtn').innerHTML = '<i class="fas fa-play"></i> Resume';

        const statusDot = document.querySelector('.status-dot');
        statusDot.classList.remove('recording');
        statusDot.classList.add('paused');
        document.querySelector('#statusIndicator span').textContent = 'Paused';

        clearInterval(timerInterval);
    } else {
        socket.emit('resume_recording');
        document.getElementById('pauseBtn').innerHTML = '<i class="fas fa-pause"></i> Pause';

        const statusDot = document.querySelector('.status-dot');
        statusDot.classList.remove('paused');
        statusDot.classList.add('recording');
        document.querySelector('#statusIndicator span').textContent = 'Recording...';

        startTimer();
    }
}

function startTimer() {
    startTime = Date.now() - elapsedTime;
    timerInterval = setInterval(updateTimer, 1000);
}

function stopTimer() {
    clearInterval(timerInterval);
    elapsedTime = 0;
    document.getElementById('timer').textContent = '00:00:00';
}

function updateTimer() {
    if (!isPaused) {
        elapsedTime = Date.now() - startTime;
        document.getElementById('timer').textContent = formatTime(elapsedTime);
    }
}

function formatTime(milliseconds) {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const hours   = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

// Generate summary on demand (live recording)
async function generateLiveSummary() {
    const analysisDiv = document.getElementById('analysis');
    analysisDiv.innerHTML = '<div class="loading">🤖 Generating AI summary... This may take 10-30 seconds.</div>';

    try {
        const response = await fetch('/api/generate-summary', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider: 'groq' })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Summary generation failed');
        }

        const result = await response.json();
        analysisDiv.innerHTML = '';

        const summaryBlock = document.createElement('div');
        summaryBlock.className = 'analysis-item';
        summaryBlock.innerHTML = renderAnalysis(result);
        analysisDiv.appendChild(summaryBlock);

        if (result.actions && result.actions.length > 0) {
            const actions = document.createElement('div');
            actions.className = 'analysis-item';
            actions.innerHTML = `<h4>✅ Action Items</h4>${formatActions(result.actions)}`;
            analysisDiv.appendChild(actions);
        }

        if (result.decisions && result.decisions.length > 0) {
            const decisions = document.createElement('div');
            decisions.className = 'analysis-item';
            decisions.innerHTML = bulletSection('🎯 Decisions', result.decisions);
            analysisDiv.appendChild(decisions);
        }

        const successMsg = document.createElement('div');
        successMsg.className = 'analysis-item';
        successMsg.style.color = '#4CAF50';
        successMsg.innerHTML = `<strong>✅ Summary saved!</strong> Check "My Notes" section to download.`;
        analysisDiv.appendChild(successMsg);

    } catch (error) {
        analysisDiv.innerHTML = `
            <div class="analysis-item" style="color: #f44336;">
                <strong>❌ Error:</strong> ${error.message}
                <br><br>
                <button class="btn-primary" onclick="generateLiveSummary()">
                    <i class="fas fa-redo"></i> Try Again
                </button>
            </div>
        `;
    }
}

function getSpeakerColor(speaker) {
    const colors = {
        'Speaker 1': '#4CAF50',
        'Speaker 2': '#2196F3',
        'Speaker 3': '#FF9800',
        'Speaker 4': '#E91E63',
        'Speaker A': '#4CAF50',
        'Speaker B': '#2196F3',
        'Speaker C': '#FF9800',
        'Speaker D': '#E91E63',
        'Analyzing...': '#9E9E9E',
    };
    return colors[speaker] || '#9C27B0';
}

// Renders a transcript string into one colored entry per speaker turn when
// it's in the "Speaker X: ..." per-line format (AssemblyAI upload path).
// Falls back to plain text for an unlabeled, flat transcript (Groq path).
function renderSpeakerTranscript(container, text) {
    if (!text) {
        container.textContent = 'No transcript available';
        return;
    }

    const lines = text.split('\n').filter(line => line.trim());
    const speakerLine = /^(Speaker\s+\S+):\s*(.*)$/;
    const parsed = lines.map(line => line.match(speakerLine));

    if (lines.length > 1 && parsed.every(Boolean)) {
        container.innerHTML = '';
        parsed.forEach(match => {
            const [, speaker, utterance] = match;
            const div = document.createElement('div');
            div.className = 'transcript-entry';

            const label = document.createElement('span');
            label.className = 'speaker-label';
            label.style.color = getSpeakerColor(speaker);
            label.textContent = speaker + ':';

            div.appendChild(label);
            div.appendChild(document.createTextNode(' ' + utterance));
            container.appendChild(div);
        });
    } else {
        container.textContent = text;
    }
}

function showSpeakerAnalysisStatus(message) {
    const transcriptDiv = document.getElementById('transcript');
    const existing = document.getElementById('speakerAnalysisBanner');
    if (existing) existing.remove();

    const banner = document.createElement('div');
    banner.id = 'speakerAnalysisBanner';
    banner.style.cssText = 'background:#fff8e1;border:1px solid #ffc107;border-radius:8px;padding:10px 16px;margin-bottom:10px;font-weight:600;color:#856404;';
    banner.textContent = '🔍 ' + message;
    transcriptDiv.insertBefore(banner, transcriptDiv.firstChild);
}

function hideSpeakerAnalysisStatus() {
    const banner = document.getElementById('speakerAnalysisBanner');
    if (banner) banner.remove();
}

function rerenderTranscript(transcript) {
    const transcriptDiv = document.getElementById('transcript');
    transcriptDiv.innerHTML = '';

    if (!transcript || transcript.length === 0) {
        transcriptDiv.innerHTML = '<div class="placeholder">No transcript available.</div>';
        return;
    }

    transcript.forEach(entry => {
        const div = document.createElement('div');
        div.className = 'transcript-entry';

        let speakerHtml = '';
        if (entry.speaker) {
            const color = getSpeakerColor(entry.speaker);
            speakerHtml = `<span class="speaker-label" style="color:${color};">${entry.speaker}:</span> `;
        }

        div.innerHTML = `<strong>[${entry.timestamp}]</strong> ${speakerHtml}${entry.text}`;
        transcriptDiv.appendChild(div);
    });

    transcriptDiv.scrollTop = transcriptDiv.scrollHeight;
}

function setupSocketEvents() {
    socket.on('connect', () => {
        console.log('Connected to server');
    });

    socket.on('transcript_update', (data) => {
        const transcriptDiv = document.getElementById('transcript');
        const placeholder = transcriptDiv.querySelector('.placeholder');
        if (placeholder) placeholder.remove();

        const newEntry = document.createElement('div');
        newEntry.className = 'transcript-entry';

        let speakerHtml = '';
        if (data.speaker) {
            const color = getSpeakerColor(data.speaker);
            speakerHtml = `<span class="speaker-label" style="color:${color};">${data.speaker}:</span> `;
        }

        newEntry.innerHTML = `<strong>[${data.timestamp}]</strong> ${speakerHtml}${data.text}`;
        transcriptDiv.appendChild(newEntry);
        transcriptDiv.scrollTop = transcriptDiv.scrollHeight;
    });

    socket.on('recording_complete', (data) => {
        const analysisDiv = document.getElementById('analysis');
        analysisDiv.innerHTML = `
            <div class="analysis-item" style="text-align: center; padding: 30px;">
                <p style="font-size: 1.1rem; margin-bottom: 20px;">${data.message}</p>
                <button class="btn-primary" onclick="generateLiveSummary()" style="font-size: 1rem; padding: 12px 24px;">
                    <i class="fas fa-magic"></i> Generate AI Summary
                </button>
            </div>
        `;
    });

    socket.on('recording_status', (data) => {
        const statusSpan = document.querySelector('#statusIndicator span');
        if (statusSpan) statusSpan.textContent = data.status;
    });

    socket.on('speaker_detection_start', (data) => {
        showSpeakerAnalysisStatus(data.message);
    });

    socket.on('speaker_detection_complete', (data) => {
        rerenderTranscript(data.transcript);
        hideSpeakerAnalysisStatus();
    });

    socket.on('url_processing_status', (data) => {
        const statusDiv = document.getElementById('urlStatus');
        if (statusDiv) statusDiv.innerHTML = '🤖 ' + data.message;
    });

    socket.on('error', (data) => {
        alert('Error: ' + data.message);
    });
}

// URL Transcription
async function processVideoUrl() {
    const urlInput = document.getElementById('videoUrl');
    const url = urlInput.value.trim();
    const btn = document.getElementById('urlProcessBtn');
    const statusDiv = document.getElementById('urlStatus');

    if (!url) {
        alert('Please paste a video URL');
        return;
    }

    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Downloading...';
    statusDiv.style.display = 'block';
    statusDiv.className = 'url-status processing';
    statusDiv.innerHTML = '📥 Downloading audio...';

    try {
        const response = await fetch('/api/process-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url, generateSummary: true, model: 'groq' })
        });

        const result = await response.json();

        if (!response.ok) throw new Error(result.error || 'Processing failed');

        statusDiv.className = 'url-status success';
        statusDiv.innerHTML = `✅ Done! Transcribed: "${result.title}"`;

        window.lastResult = result;
        showResults(result);
        urlInput.value = '';

    } catch (error) {
        statusDiv.className = 'url-status error';
        statusDiv.textContent = '❌ ' + error.message;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-download"></i> Transcribe';
    }
}

// File Upload
function setupFileUpload() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) handleFile(e.target.files[0]);
    });
}

function handleFile(file) {
    const validTypes = ['audio/', 'video/'];
    if (!validTypes.some(type => file.type.startsWith(type))) {
        alert('Please upload an audio or video file!');
        return;
    }

    const maxSize = 1024 * 1024 * 1024;
    if (file.size > maxSize) {
        alert(`File is too large! Maximum size is 1GB.\n\nYour file: ${formatFileSize(file.size)}\n\nPlease compress your video or extract audio only.`);
        return;
    }

    if (file.size > 100 * 1024 * 1024) {
        if (!confirm(`This file is ${formatFileSize(file.size)}. Processing may take several minutes. Continue?`)) return;
    }

    selectedFile = file;

    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = formatFileSize(file.size);
    document.getElementById('fileInfo').style.display = 'block';
    document.getElementById('processBtn').disabled = false;

    const dropZone = document.getElementById('dropZone');
    dropZone.innerHTML = `
        <i class="fas fa-check-circle" style="color: #4CAF50;"></i>
        <h3>File selected</h3>
        <p>${file.name}</p>
        <p class="file-types">Ready to process (${formatFileSize(file.size)})</p>
    `;
}

function clearFile() {
    selectedFile = null;
    document.getElementById('fileInfo').style.display = 'none';
    document.getElementById('processBtn').disabled = true;
    document.getElementById('dropZone').innerHTML = `
        <i class="fas fa-cloud-upload-alt"></i>
        <h3>Drop your files here</h3>
        <p>or click to browse</p>
        <p class="file-types">Supported: MP3, WAV, M4A, MP4, AVI, MOV</p>
    `;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

async function processFile() {
    if (!selectedFile) return;

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('generateSummary', document.getElementById('generateSummary').checked);
    formData.append('extractActions', document.getElementById('extractActions').checked);
    formData.append('detectDecisions', document.getElementById('detectDecisions').checked);
    formData.append('model', document.getElementById('modelSelect').value);

    document.getElementById('progressContainer').style.display = 'block';
    updateProgress(0, 'Uploading file...');

    try {
        const response = await fetch('/api/process-file', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            let message = 'Processing failed';
            try {
                const errorBody = await response.json();
                if (errorBody && errorBody.error) message = errorBody.error;
            } catch (e) {
                // response body wasn't JSON — keep the generic message
            }
            throw new Error(message);
        }

        const result = await response.json();
        updateProgress(100, 'Processing complete!');
        showResults(result);

    } catch (error) {
        alert('Error processing file: ' + error.message);
        updateProgress(0, 'Error occurred');
    }
}

function updateProgress(percent, text) {
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const steps = document.querySelectorAll('.step');

    progressFill.style.width = percent + '%';
    progressText.textContent = text;

    steps.forEach((step, index) => {
        step.classList.remove('active', 'completed');
        if (index * 25 < percent) {
            step.classList.add('completed');
        } else if (index * 25 === Math.floor(percent / 25) * 25) {
            step.classList.add('active');
        }
    });
}

function showResults(result) {
    renderSpeakerTranscript(document.getElementById('fileTranscript'), result.transcript);
    document.getElementById('fileSummary').innerHTML = renderAnalysis(result);
    document.getElementById('fileActions').innerHTML = formatActions(result.actions);
    document.getElementById('resultsContainer').style.display = 'block';
    window.lastResult = result;

    // Chat works off window.lastResult directly (sent inline with each
    // question), so it's available immediately even if the note was never
    // persisted server-side — e.g. STATELESS/cloud deployments.
    currentChatNoteId = 'current';
    resetChatUI();
}

// Shared by the just-generated results view and the saved-note detail view.
function resetChatUI() {
    chatHistory = [];
    const chatMessages = document.getElementById('chatMessages');
    if (chatMessages) {
        chatMessages.innerHTML = `
            <div class="chat-welcome">
                <i class="fas fa-robot"></i>
                <p>Ask me anything about this meeting!</p>
                <div class="chat-suggestions">
                    <button onclick="askSuggestion('What were the main decisions made?')">What were the main decisions?</button>
                    <button onclick="askSuggestion('What are the action items?')">What are the action items?</button>
                    <button onclick="askSuggestion('Give me a brief summary')">Give me a brief summary</button>
                    <button onclick="askSuggestion('What questions were raised?')">What questions were raised?</button>
                </div>
            </div>`;
    }
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatSummary(summary) {
    if (!summary) return '<p>No summary available</p>';
    return escapeHtml(summary)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

function bulletSection(title, items) {
    if (!items || items.length === 0) return '';
    const lis = items.map(item => `<li>${escapeHtml(item)}</li>`).join('');
    return `<div class="summary-section"><h4>${title}</h4><ul>${lis}</ul></div>`;
}

function tagSection(title, items) {
    if (!items || items.length === 0) return '';
    const tags = items.map(item => `<span class="topic-tag">${escapeHtml(item)}</span>`).join('');
    return `<div class="summary-section"><h4>${title}</h4><div class="topic-tags">${tags}</div></div>`;
}

// Combines the paragraph summary with the structured fields (key points,
// topics, questions, next steps, insights) the backend already generates
// but were previously discarded by the UI — keeps a long summary from
// reading as one dense block of text.
function renderAnalysis(result) {
    if (!result || !result.summary) return '<p>No summary available</p>';

    let html = `<div class="summary-section summary-overview">${formatSummary(result.summary)}</div>`;
    html += bulletSection('🔑 Key Points', result.key_points);
    html += tagSection('🏷️ Topics', result.topics);
    html += bulletSection('❓ Questions Raised', result.questions_raised);
    html += bulletSection('➡️ Next Steps', result.next_steps);
    html += bulletSection('💡 Insights', result.insights);
    return html;
}

function formatActions(actions) {
    if (!actions || actions.length === 0) return '<p>No action items found</p>';
    let html = '<ul class="actions-list">';
    actions.forEach(action => {
        html += `<li><i class="fas fa-check-circle"></i> ${escapeHtml(action)}</li>`;
    });
    html += '</ul>';
    return html;
}

function downloadResults() {
    if (!window.lastResult) {
        alert('No results to download!');
        return;
    }

    const content = `
MEETING NOTES
=============

TRANSCRIPT:
${window.lastResult.transcript || ''}

SUMMARY:
${window.lastResult.summary || ''}

KEY POINTS:
${(window.lastResult.key_points || []).map(p => '- ' + p).join('\n')}

ACTION ITEMS:
${(window.lastResult.actions || []).map(a => '- ' + a).join('\n')}

DECISIONS:
${(window.lastResult.decisions || []).map(d => '- ' + d).join('\n')}

Generated by Smart Meeting Notes
Date: ${new Date().toLocaleString()}
    `;

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `meeting_notes_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Notes Management
async function loadNotes() {
    try {
        const response = await fetch('/api/notes');
        const notes = await response.json();

        const notesGrid = document.getElementById('notesGrid');
        notesGrid.innerHTML = '';

        if (notes.length === 0) {
            notesGrid.innerHTML = '<div class="loading" style="border:none;">No saved notes yet.</div>';
            return;
        }

        notes.forEach(note => {
            // A real <a target="_blank"> so ctrl/cmd/middle-click all work
            // the normal browser way — the note opens in its own tab on
            // /notes/<id>, keeping this list untouched.
            const noteLink = document.createElement('a');
            noteLink.className = 'note-card';
            noteLink.href = `/notes/${encodeURIComponent(note.id)}`;
            noteLink.target = '_blank';
            noteLink.rel = 'noopener noreferrer';
            noteLink.innerHTML = `
                <button type="button" class="note-delete-btn" title="Delete note" aria-label="Delete note">
                    <i class="fas fa-trash"></i>
                </button>
                <div class="note-header">
                    <div class="note-title">${escapeHtml(note.title)}</div>
                    <div class="note-date">${escapeHtml(note.date)}</div>
                </div>
                <div class="note-preview">${escapeHtml(note.preview)}</div>
                <div class="note-meta">
                    <span><i class="fas fa-clock"></i> ${escapeHtml(note.duration)}</span>
                    <span><i class="fas fa-file"></i> ${escapeHtml(note.type)}</span>
                </div>
            `;
            noteLink.querySelector('.note-delete-btn').addEventListener('click', (evt) => {
                evt.preventDefault();
                evt.stopPropagation();
                deleteNoteFromCard(note.id, noteLink);
            });
            notesGrid.appendChild(noteLink);
        });
    } catch (error) {
        console.error('Error loading notes:', error);
    }
}

async function loadNoteDetails(noteId) {
    // Reset chat state for the newly selected note
    currentChatNoteId = noteId;
    resetChatUI();

    try {
        const response = await fetch(`/api/notes/${noteId}`);
        const note = await response.json();

        if (!response.ok) {
            document.getElementById('detailTitle').textContent = note.error || 'Note not found';
            document.getElementById('noteDetails').style.display = 'block';
            return;
        }

        // Chat sends the transcript/summary inline, sourced from here.
        window.lastResult = note;

        document.getElementById('detailTitle').textContent = note.title || 'Meeting Notes';
        document.getElementById('detailDate').textContent = note.date || 'N/A';
        document.getElementById('detailDuration').textContent = note.duration || 'N/A';
        document.getElementById('detailType').textContent = note.type || 'N/A';
        document.getElementById('detailSize').textContent = note.size || 'N/A';

        renderSpeakerTranscript(document.getElementById('detailTranscriptContent'), note.transcript);
        document.getElementById('detailSummaryContent').innerHTML = renderAnalysis(note);
        document.getElementById('detailActionsContent').innerHTML = formatActions(note.actions);
        document.getElementById('detailAnalysisContent').textContent = note.analysis || 'No analysis available';

        document.getElementById('noteDetails').style.display = 'block';

    } catch (error) {
        console.error('Error loading note details:', error);
    }
}

function switchDetailTab(tabId, evt) {
    document.querySelectorAll('.detail-pane').forEach(tab => {
        tab.classList.remove('active');
    });

    document.querySelectorAll('.note-content-tabs .tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    document.getElementById(tabId).classList.add('active');

    const e = evt || window.event;
    if (e && e.currentTarget) {
        e.currentTarget.classList.add('active');
    }
}

function downloadSelectedNote() {
    if (!selectedNote) {
        alert('Please select a note first!');
        return;
    }
    window.location.href = `/api/notes/${selectedNote}/download`;
}

async function deleteNoteFromCard(noteId, cardEl) {
    if (!confirm('Are you sure you want to delete this note?')) return;

    try {
        const response = await fetch(`/api/notes/${noteId}`, { method: 'DELETE' });
        if (response.ok) {
            cardEl.remove();
            const notesGrid = document.getElementById('notesGrid');
            if (notesGrid && notesGrid.children.length === 0) {
                notesGrid.innerHTML = '<div class="loading" style="border:none;">No saved notes yet.</div>';
            }
        } else {
            alert('Failed to delete note.');
        }
    } catch (error) {
        console.error('Error deleting note:', error);
        alert('Failed to delete note.');
    }
}

async function deleteSelectedNote() {
    if (!selectedNote || !confirm('Are you sure you want to delete this note?')) return;

    try {
        const response = await fetch(`/api/notes/${selectedNote}`, { method: 'DELETE' });
        if (response.ok) {
            selectedNote = null;
            if (document.getElementById('notesGrid')) {
                // On the My Notes page — refresh the grid.
                loadNotes();
                document.getElementById('noteDetails').style.display = 'none';
            } else {
                // Standalone /notes/<id> tab — nothing to refresh, just say so.
                document.getElementById('detailTitle').textContent = 'Note deleted';
                document.getElementById('noteDetails').querySelector('.note-content-tabs').style.display = 'none';
                document.getElementById('noteDetails').querySelector('.note-content').style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error deleting note:', error);
    }
}

function switchTab(tabId, evt) {
    document.querySelectorAll('.tab-pane').forEach(tab => {
        tab.classList.remove('active');
    });

    document.querySelectorAll('.results-tabs .tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });

    document.getElementById(tabId).classList.add('active');

    const e = evt || window.event;
    if (e && e.currentTarget) {
        e.currentTarget.classList.add('active');
    }
}

// Chat with Meeting
function askSuggestion(question) {
    document.getElementById('chatInput').value = question;
    sendChatMessage();
}

async function sendChatMessage() {
    const input = document.getElementById('chatInput');
    const question = input.value.trim();
    const sendBtn = document.getElementById('chatSendBtn');

    if (!question) return;
    if (!currentChatNoteId) {
        alert('Please select a note first');
        return;
    }

    appendChatMessage('user', question);
    input.value = '';
    sendBtn.disabled = true;

    const typingId = appendTypingIndicator();

    try {
        const response = await fetch(`/api/notes/${currentChatNoteId}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question: question,
                history: chatHistory,
                transcript: window.lastResult ? window.lastResult.transcript : '',
                summary: window.lastResult ? window.lastResult.summary : ''
            })
        });

        const data = await response.json();
        removeTypingIndicator(typingId);

        if (!response.ok) throw new Error(data.error || 'Chat failed');

        chatHistory.push({ role: 'user', content: question });
        chatHistory.push({ role: 'assistant', content: data.answer });

        appendChatMessage('assistant', data.answer);

    } catch (error) {
        removeTypingIndicator(typingId);
        appendChatMessage('error', `Error: ${error.message}`);
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}

function appendChatMessage(role, content) {
    const messagesDiv = document.getElementById('chatMessages');

    const welcome = messagesDiv.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message chat-${role}`;

    const formattedContent = content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/^- (.*$)/gm, '<li>$1</li>')
        .replace(/\n/g, '<br>');

    if (role === 'user') {
        msgDiv.innerHTML = `
            <div class="chat-bubble user-bubble">${formattedContent}</div>
            <div class="chat-avatar user-avatar"><i class="fas fa-user"></i></div>
        `;
    } else if (role === 'assistant') {
        msgDiv.innerHTML = `
            <div class="chat-avatar bot-avatar"><i class="fas fa-robot"></i></div>
            <div class="chat-bubble bot-bubble">${formattedContent}</div>
        `;
    } else {
        msgDiv.innerHTML = `<div class="chat-bubble error-bubble">${formattedContent}</div>`;
    }

    messagesDiv.appendChild(msgDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function appendTypingIndicator() {
    const messagesDiv = document.getElementById('chatMessages');
    const id = 'typing-' + Date.now();
    const div = document.createElement('div');
    div.id = id;
    div.className = 'chat-message chat-assistant';
    div.innerHTML = `
        <div class="chat-avatar bot-avatar"><i class="fas fa-robot"></i></div>
        <div class="chat-bubble bot-bubble typing-indicator">
            <span></span><span></span><span></span>
        </div>
    `;
    messagesDiv.appendChild(div);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return id;
}

function removeTypingIndicator(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

async function autoDetectDevice() {
    const btn = event.target;
    const originalText = btn.innerHTML;

    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Detecting... (Play some audio now)';
    btn.disabled = true;

    try {
        const response = await fetch('/api/auto-detect-device');
        const result = await response.json();

        if (result.success) {
            const deviceList = document.getElementById('deviceList');
            deviceList.value = result.device_id;

            btn.innerHTML = '<i class="fas fa-check-circle"></i> Device Detected!';
            btn.style.backgroundColor = '#4CAF50';

            alert(`✅ Detected: ${result.device_name}\nAudio level: ${(result.level * 100).toFixed(2)}%\n\nChange the dropdown selection if needed.`);

            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.style.backgroundColor = '';
                btn.disabled = false;
            }, 3000);
        } else {
            throw new Error(result.message || 'Detection failed');
        }

    } catch (error) {
        alert(`❌ ${error.message}\n\nTips:\n- Make sure audio is playing\n- Try adjusting volume\n- Manually select a device instead`);
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}
