// Global variables
let socket;
let isRecording = false;
let isPaused = false;
let timerInterval;
let startTime;
let elapsedTime = 0;
let selectedFile = null;
let selectedNote = null;

// Initialize when page loads
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Socket.IO
    socket = io();
    
    // Setup event listeners
    setupNavigation();
    setupFileUpload();
    loadAudioDevices();
    setupSocketEvents();
    
    // Show home section by default
    switchSection('home');
});

// Navigation
function setupNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const target = this.getAttribute('href').substring(1);
            switchSection(target);
            
            // Update active nav link
            navLinks.forEach(l => l.classList.remove('active'));
            this.classList.add('active');

            // FIX 6: Load notes when the user navigates to the notes section
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

    // FIX 7: Also trigger loadNotes if navigating programmatically (e.g. feature card button)
    if (sectionId === 'notes') {
        loadNotes();
    }
}

// Audio Capture
// FIX 8: selectOption now receives the event explicitly instead of relying on the global `event`
function selectOption(option, evt) {
    const cards = document.querySelectorAll('.option-card');
    cards.forEach(card => card.classList.remove('selected'));
    // Use evt if passed, otherwise fall back to window.event for legacy support
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
        deviceList.innerHTML = '';
        
        devices.forEach(device => {
            const deviceElement = document.createElement('div');
            deviceElement.className = 'device-item';
            deviceElement.innerHTML = `
                <div class="device-name">${device.name}</div>
                <div class="device-info">Inputs: ${device.inputs} | Sample Rate: ${device.rate}Hz</div>
            `;
            deviceElement.addEventListener('click', () => selectDevice(device.id, deviceElement));
            deviceList.appendChild(deviceElement);
        });
    } catch (error) {
        console.error('Error loading devices:', error);
    }
}

function selectDevice(deviceId, element) {
    document.querySelectorAll('.device-item').forEach(item => {
        item.classList.remove('selected');
    });
    element.classList.add('selected');
}

function startRecording() {
    const selectedOption = document.querySelector('input[name="captureOption"]:checked');
    if (!selectedOption) {
        alert('Please select a capture option first!');
        return;
    }
    
    const selectedDevice = document.querySelector('.device-item.selected');
    if (!selectedDevice) {
        alert('Please select an audio device!');
        return;
    }
    
    const captureType = selectedOption.value;
    const deviceId = Array.from(document.querySelectorAll('.device-item')).indexOf(selectedDevice);
    
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
        const formattedTime = formatTime(elapsedTime);
        document.getElementById('timer').textContent = formattedTime;
    }
}

function formatTime(milliseconds) {
    const totalSeconds = Math.floor(milliseconds / 1000);
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
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
        
        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFile(e.target.files[0]);
        }
    });
}

function handleFile(file) {
    const validTypes = ['audio/', 'video/'];
    if (!validTypes.some(type => file.type.startsWith(type))) {
        alert('Please upload an audio or video file!');
        return;
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
        <p class="file-types">Ready to process</p>
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
        
        if (!response.ok) throw new Error('Processing failed');
        
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
    document.getElementById('fileTranscript').textContent = result.transcript || 'No transcript available';
    document.getElementById('fileSummary').innerHTML = formatSummary(result.summary);
    document.getElementById('fileActions').innerHTML = formatActions(result.actions);
    
    document.getElementById('resultsContainer').style.display = 'block';
    
    window.lastResult = result;
}

function formatSummary(summary) {
    if (!summary) return '<p>No summary available</p>';
    
    return summary
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^### (.*$)/gm, '<h3>$1</h3>')
        .replace(/^## (.*$)/gm, '<h2>$1</h2>')
        .replace(/^# (.*$)/gm, '<h1>$1</h1>')
        .replace(/^- (.*$)/gm, '<li>$1</li>')
        .replace(/\n/g, '<br>');
}

function formatActions(actions) {
    if (!actions || actions.length === 0) {
        return '<p>No action items found</p>';
    }
    
    let html = '<ul class="actions-list">';
    actions.forEach(action => {
        html += `<li><i class="fas fa-check-circle"></i> ${action}</li>`;
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

ACTION ITEMS:
${(window.lastResult.actions || []).map(a => '- ' + a).join('\n')}

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
            const noteElement = document.createElement('div');
            noteElement.className = 'note-card';
            noteElement.innerHTML = `
                <div class="note-header">
                    <div class="note-title">${note.title}</div>
                    <div class="note-date">${note.date}</div>
                </div>
                <div class="note-preview">${note.preview}</div>
                <div class="note-meta">
                    <span><i class="fas fa-clock"></i> ${note.duration}</span>
                    <span><i class="fas fa-file"></i> ${note.type}</span>
                </div>
            `;
            
            noteElement.addEventListener('click', () => selectNote(note.id, noteElement));
            notesGrid.appendChild(noteElement);
        });
    } catch (error) {
        console.error('Error loading notes:', error);
    }
}

function selectNote(noteId, element) {
    document.querySelectorAll('.note-card').forEach(card => {
        card.classList.remove('selected');
    });
    element.classList.add('selected');
    selectedNote = noteId;
    
    loadNoteDetails(noteId);
}

async function loadNoteDetails(noteId) {
    try {
        const response = await fetch(`/api/notes/${noteId}`);
        const note = await response.json();
        
        document.getElementById('detailTitle').textContent = note.title || 'Meeting Notes';
        document.getElementById('detailDate').textContent = note.date || 'N/A';
        document.getElementById('detailDuration').textContent = note.duration || 'N/A';
        document.getElementById('detailType').textContent = note.type || 'N/A';
        document.getElementById('detailSize').textContent = note.size || 'N/A';
        
        document.getElementById('detailTranscriptContent').textContent = note.transcript || 'No transcript available';
        document.getElementById('detailSummaryContent').innerHTML = formatSummary(note.summary);
        document.getElementById('detailActionsContent').innerHTML = formatActions(note.actions);
        document.getElementById('detailAnalysisContent').textContent = note.analysis || 'No analysis available';
        
        document.getElementById('noteDetails').style.display = 'block';
        
    } catch (error) {
        console.error('Error loading note details:', error);
    }
}

// FIX 9: switchDetailTab and switchTab now receive evt explicitly — no more reliance on bare global `event`
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

async function deleteSelectedNote() {
    if (!selectedNote || !confirm('Are you sure you want to delete this note?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/notes/${selectedNote}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadNotes();
            document.getElementById('noteDetails').style.display = 'none';
            selectedNote = null;
        }
    } catch (error) {
        console.error('Error deleting note:', error);
    }
}

// FIX 10: switchTab also receives evt explicitly
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

// Socket.IO events
function setupSocketEvents() {
    socket.on('connect', () => {
        console.log('Connected to server');
    });
    
    socket.on('transcript_update', (data) => {
        const transcriptDiv = document.getElementById('transcript');
        // Remove placeholder on first entry
        const placeholder = transcriptDiv.querySelector('.placeholder');
        if (placeholder) placeholder.remove();

        const newEntry = document.createElement('div');
        newEntry.className = 'transcript-entry';
        newEntry.innerHTML = `<strong>[${data.timestamp}]</strong> ${data.text}`;
        transcriptDiv.appendChild(newEntry);
        transcriptDiv.scrollTop = transcriptDiv.scrollHeight;
    });
    
    socket.on('analysis_update', (data) => {
        const analysisDiv = document.getElementById('analysis');
        analysisDiv.innerHTML = '';
        
        if (data.summary) {
            const summary = document.createElement('div');
            summary.className = 'analysis-item';
            summary.innerHTML = `<strong>📝 Summary:</strong> ${data.summary}`;
            analysisDiv.appendChild(summary);
        }
        
        if (data.actions && data.actions.length > 0) {
            const actions = document.createElement('div');
            actions.className = 'analysis-item';
            actions.innerHTML = `<strong>✅ Actions:</strong><br>${data.actions.map(a => `• ${a}`).join('<br>')}`;
            analysisDiv.appendChild(actions);
        }
        
        analysisDiv.scrollTop = analysisDiv.scrollHeight;
    });
    
    socket.on('recording_status', (data) => {
        const statusSpan = document.querySelector('#statusIndicator span');
        statusSpan.textContent = data.status;
    });
    
    socket.on('error', (data) => {
        alert('Error: ' + data.message);
    });
}