// translator.js — full real-time translation logic

const socket = io();

let translatorActive = false;
let translatorPaused = false;
let timerInterval   = null;
let timerSeconds    = 0;
let translatorSegments = [];   // {original, translated, source_lang, source_lang_name, target_lang, was_translated, speaker, timestamp}
let lastDetectedLang   = null;

// ── Device loading ────────────────────────────────────────

async function loadTranslatorDevices() {
    const sel = document.getElementById('translatorDevice');
    try {
        const res     = await fetch('/api/devices');
        const devices = await res.json();
        sel.innerHTML = '';

        if (!Array.isArray(devices) || devices.length === 0) {
            sel.innerHTML = '<option value="">No input devices found</option>';
            return;
        }

        devices.forEach(d => {
            const opt = document.createElement('option');
            opt.value       = d.id;
            opt.textContent = d.name;
            sel.appendChild(opt);
        });
    } catch (e) {
        sel.innerHTML = '<option value="">Error loading devices</option>';
        console.error('Device load error:', e);
    }
}

// ── Timer ─────────────────────────────────────────────────

function startTimer() {
    timerSeconds = 0;
    timerInterval = setInterval(() => {
        if (!translatorPaused) {
            timerSeconds++;
        }
        const h = String(Math.floor(timerSeconds / 3600)).padStart(2, '0');
        const m = String(Math.floor((timerSeconds % 3600) / 60)).padStart(2, '0');
        const s = String(timerSeconds % 60).padStart(2, '0');
        document.getElementById('translatorTimer').textContent = `${h}:${m}:${s}`;
    }, 1000);
}

function stopTimer() {
    clearInterval(timerInterval);
    timerInterval = null;
}

function resetTimer() {
    stopTimer();
    timerSeconds = 0;
    document.getElementById('translatorTimer').textContent = '00:00:00';
}

// ── Status indicator ──────────────────────────────────────

function setStatus(text, state) {
    const wrap = document.getElementById('translatorStatusDot');
    const span = document.getElementById('translatorStatusText');
    span.textContent = text;
    wrap.className   = 'status-dot-wrap ' + (state || '');
}

// ── Panel helpers ─────────────────────────────────────────

function escHtml(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function clearPanels() {
    document.getElementById('originalContent').innerHTML =
        '<div class="panel-placeholder">Original speech will appear here…</div>';
    document.getElementById('translatedContent').innerHTML =
        '<div class="panel-placeholder">Translation will appear here…</div>';
}

function appendSegment(seg) {
    const origBox  = document.getElementById('originalContent');
    const transBox = document.getElementById('translatedContent');

    // Remove placeholders on first entry
    const ph1 = origBox.querySelector('.panel-placeholder');
    const ph2 = transBox.querySelector('.panel-placeholder');
    if (ph1) ph1.remove();
    if (ph2) ph2.remove();

    // Original
    const origDiv = document.createElement('div');
    origDiv.className = 'segment-entry';
    origDiv.innerHTML =
        `<span class="seg-time">${escHtml(seg.timestamp)}</span>` +
        `<span class="seg-text">${escHtml(seg.original)}</span>`;
    origBox.appendChild(origDiv);
    origBox.scrollTop = origBox.scrollHeight;

    // Translated
    const transDiv = document.createElement('div');
    transDiv.className = 'segment-entry';
    if (seg.was_translated) {
        transDiv.innerHTML =
            `<span class="seg-time">${escHtml(seg.timestamp)}</span>` +
            `<span class="seg-text">🌐 ${escHtml(seg.translated)}</span>`;
    } else {
        transDiv.innerHTML =
            `<span class="seg-time">${escHtml(seg.timestamp)}</span>` +
            `<span class="seg-text seg-no-translation">— No translation needed</span>`;
    }
    transBox.appendChild(transDiv);
    transBox.scrollTop = transBox.scrollHeight;
}

// ── UI state ──────────────────────────────────────────────

function setRecordingUI(active) {
    document.getElementById('startTranslatorBtn').disabled   = active;
    document.getElementById('stopTranslatorBtn').disabled    = !active;
    document.getElementById('pauseTranslatorBtn').disabled   = !active;
    document.getElementById('sourceLang').disabled           = active;
    document.getElementById('targetLang').disabled           = active;
    document.getElementById('translatorDevice').disabled     = active;
}

// ── Start ─────────────────────────────────────────────────

function startTranslator() {
    const deviceId   = parseInt(document.getElementById('translatorDevice').value, 10);
    const sourceLang = document.getElementById('sourceLang').value;
    const targetLang = document.getElementById('targetLang').value;

    if (isNaN(deviceId)) {
        alert('Please select an audio device.');
        return;
    }

    // Reset state
    translatorSegments = [];
    lastDetectedLang   = null;
    clearPanels();
    resetTimer();

    // Update column labels (use display text, not ISO code values)
    const sourceLangEl = document.getElementById('sourceLang');
    const targetLangEl = document.getElementById('targetLang');
    document.getElementById('originalColLabel').textContent =
        sourceLang === 'auto' ? 'Original (auto-detect)' : sourceLangEl.options[sourceLangEl.selectedIndex].text;
    document.getElementById('translatedColLabel').textContent =
        targetLangEl.options[targetLangEl.selectedIndex].text;

    // Hide detected-lang badge
    const badge = document.getElementById('detectedLangBadge');
    badge.style.display = 'none';
    badge.textContent   = '';

    // Disable action buttons until first segment arrives
    document.getElementById('copyTranslationBtn').disabled    = true;
    document.getElementById('saveTranslatorNoteBtn').disabled = true;

    socket.emit('start_translator', { deviceId, sourceLang, targetLang });

    // Show loading notice — model may need to warm up on first use
    const loadingMsg = document.getElementById('translatorLoadingMsg');
    if (loadingMsg) loadingMsg.style.display = 'block';
}

// ── Stop ──────────────────────────────────────────────────

function stopTranslator() {
    socket.emit('stop_translator');
}

// ── Pause / Resume ────────────────────────────────────────

function togglePauseTranslator() {
    if (translatorPaused) {
        socket.emit('resume_translator');
    } else {
        socket.emit('pause_translator');
    }
}

// ── Copy translation ──────────────────────────────────────

function copyTranslation() {
    const text = translatorSegments.map(s => s.translated).join('\n');
    if (!text.trim()) return;

    navigator.clipboard.writeText(text).then(() => {
        const btn  = document.getElementById('copyTranslationBtn');
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        setTimeout(() => { btn.innerHTML = orig; }, 2000);
    }).catch(err => {
        console.error('Copy failed:', err);
    });
}

// ── Save as Note ──────────────────────────────────────────

function saveTranslatorNote() {
    if (!translatorSegments.length) {
        alert('No segments to save yet.');
        return;
    }

    const sourceLang = document.getElementById('sourceLang').value;
    const targetLang = document.getElementById('targetLang').value;

    const btn = document.getElementById('saveTranslatorNoteBtn');
    btn.disabled  = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving…';

    socket.emit('save_translator_note', {
        segments: translatorSegments,
        sourceLang,
        targetLang
    });
}

// ── Socket.IO events ──────────────────────────────────────

socket.on('translator_status', data => {
    const status = (data.status || '').toLowerCase();

    if (status.includes('started')) {
        translatorActive = true;
        translatorPaused = false;
        setRecordingUI(true);
        startTimer();
        setStatus('Translating…', 'active');

    } else if (status.includes('paused')) {
        translatorPaused = true;
        const btn = document.getElementById('pauseTranslatorBtn');
        btn.innerHTML = '<i class="fas fa-play"></i> Resume';
        setStatus('Paused', 'paused');

    } else if (status.includes('translating')) {
        translatorPaused = false;
        const btn = document.getElementById('pauseTranslatorBtn');
        btn.innerHTML = '<i class="fas fa-pause"></i> Pause';
        setStatus('Translating…', 'active');

    } else if (status.includes('stopped')) {
        // handled by translator_stopped event
    }
});

socket.on('translator_update', seg => {
    console.log('translator_update received:', seg.original, '→', seg.translated, 'was_translated:', seg.was_translated);

    // Hide loading message once first segment arrives
    const loadingMsg = document.getElementById('translatorLoadingMsg');
    if (loadingMsg) loadingMsg.style.display = 'none';

    translatorSegments.push(seg);
    appendSegment(seg);

    // Show auto-detected language badge
    const sourceLang = document.getElementById('sourceLang').value;
    if (sourceLang === 'auto' && seg.source_lang && seg.source_lang !== lastDetectedLang) {
        lastDetectedLang = seg.source_lang;
        const badge = document.getElementById('detectedLangBadge');
        badge.textContent   = `Detected: ${seg.source_lang_name || seg.source_lang}`;
        badge.style.display = 'inline-block';
    }

    // Enable action buttons now that we have data
    document.getElementById('copyTranslationBtn').disabled    = false;
    document.getElementById('saveTranslatorNoteBtn').disabled = false;
});

socket.on('translator_stopped', () => {
    translatorActive = false;
    translatorPaused = false;
    stopTimer();
    setRecordingUI(false);
    setStatus('Stopped', '');

    const loadingMsg = document.getElementById('translatorLoadingMsg');
    if (loadingMsg) loadingMsg.style.display = 'none';

    // Reset pause button label
    document.getElementById('pauseTranslatorBtn').innerHTML =
        '<i class="fas fa-pause"></i> Pause';
});

socket.on('translator_note_saved', data => {
    const btn = document.getElementById('saveTranslatorNoteBtn');
    btn.disabled  = false;
    btn.innerHTML = '<i class="fas fa-check"></i> Saved!';
    setTimeout(() => {
        btn.innerHTML = '<i class="fas fa-save"></i> Save as Note';
    }, 2500);
    console.log('Translator note saved:', data.filename);
});

socket.on('translator_error', data => {
    setStatus('Error', 'error');
    // If translator was starting, revert UI
    if (translatorActive) {
        translatorActive = false;
        stopTimer();
        setRecordingUI(false);
    }
    alert('Translator error: ' + (data.message || 'Unknown error'));
});

socket.on('connect', () => {
    setStatus('Ready', '');
});

socket.on('disconnect', () => {
    if (translatorActive) {
        translatorActive = false;
        stopTimer();
        setRecordingUI(false);
        setStatus('Disconnected', 'error');
    }
});

// ── Init ──────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    loadTranslatorDevices();
});
