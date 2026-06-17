// --------------------------------------------------------------------------
// Orchestration & AI Workstation Handlers
// --------------------------------------------------------------------------

// Client session ID for WebSocket progress mapping
const clientId = Math.random().toString(36).substring(7);

function setTheme(isDark) {
    if (isDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
        if (refs.moonIcon) refs.moonIcon.classList.add('hidden');
        if (refs.sunIcon) refs.sunIcon.classList.remove('hidden');
    } else {
        document.documentElement.setAttribute('data-theme', 'light');
        localStorage.setItem('theme', 'light');
        if (refs.sunIcon) refs.sunIcon.classList.add('hidden');
        if (refs.moonIcon) refs.moonIcon.classList.remove('hidden');
    }
}

// Initialize application on load
window.addEventListener('DOMContentLoaded', async () => {
    // Initialize Theme
    const savedTheme = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    setTheme(savedTheme === 'dark');
    
    if (refs.themeBtn) {
        refs.themeBtn.addEventListener('click', () => {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            setTheme(!isDark);
        });
    }

    // Load Runtime Configuration from server
    await loadConfig();
    
    // Wire up Drag and Drop for premium dropzones
    setupUploaderDragAndDrop();
    
    // Wire up Server settings modal triggers
    setupSettingsModal();
    
    // Wire up AI workstation right sidebar tabs
    setupAIWorkstationTabs();
    
    // Wire up top-level app shell tabs (Workstation / Translation)
    setupAppShellTabs();
    
    // Wire up the dedicated Translation tab
    setupTranslationTab();
    
    // Wire up AI translation & structured data extraction events
    setupAIFeatures();
    
    // Connect WebSocket progress listener immediately
    connectWS().catch((err) => {
        console.error('Progress connection failed:', err);
    });
});

// 1. WebSocket Progress Orchestration
async function ensureProgressSession() {
    if (state.progressChannelId && state.progressSessionToken) return;

    const response = await fetch('/api/progress/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client_id: clientId })
    });
    if (!response.ok) throw new Error('Could not create progress session');

    const session = await response.json();
    state.progressChannelId = session.channel_id;
    state.progressSessionToken = session.session_token;
}

async function connectWS() {
    await ensureProgressSession();
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const channel = encodeURIComponent(state.progressChannelId);
    const token = encodeURIComponent(state.progressSessionToken);
    state.ws = new WebSocket(`${protocol}//${window.location.host}/ws/${channel}?token=${token}`);
    
    state.ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.status && data.percent !== undefined) {
                updateProgress(data.status, data.percent);
                
                // Highlight corresponding stage label in progress panel
                const stage = data.stage; // 'convert' | 'detect' | 'ocr' | 'refine' | 'embed'
                if (stage) {
                    // Reset all stage weights style
                    ['stageConvert', 'stageDetect', 'stageOcr', 'stageRefine', 'stageEmbed'].forEach(k => {
                        if(refs[k]) {
                            refs[k].style.color = 'var(--text-muted)';
                            refs[k].style.fontWeight = '400';
                            const icon = refs[k].querySelector('.stage-icon-wrap');
                            if(icon) {
                                icon.style.borderColor = 'var(--border)';
                                icon.style.background = 'var(--surface)';
                            }
                        }
                    });
                    
                    const elementKey = 'stage' + stage.charAt(0).toUpperCase() + stage.slice(1);
                    const targetEl = refs[elementKey];
                    if (targetEl) {
                        targetEl.style.color = 'var(--primary)';
                        targetEl.style.fontWeight = '600';
                        const icon = targetEl.querySelector('.stage-icon-wrap');
                        if (icon) {
                            icon.style.borderColor = 'var(--primary)';
                            icon.style.background = 'rgba(139, 92, 246, 0.15)';
                        }
                    }
                }
            }
        } catch (e) {
            console.log("WS content is not JSON:", event.data);
        }
    };
    
    state.ws.onclose = () => {
        console.log("WS Disconnected. Retrying in 5 seconds...");
        if(refs.connStatus) {
            refs.connStatus.className = 'status-dot offline';
            refs.connStatus.title = 'Disconnected';
        }
        if(refs.connectionStatusDot) refs.connectionStatusDot.className = 'status-dot offline';
        setTimeout(() => { connectWS().catch(console.error); }, 5000);
    };
}

function updateProgress(message, percent) {
    if (refs.statusText) refs.statusText.textContent = message;
    if (refs.progressBar) refs.progressBar.style.width = `${percent}%`;
    if (refs.subStatus) refs.subStatus.textContent = `${percent}%`;
}

// 2. Drag & Drop & Upload Workflows
function setupUploaderDragAndDrop() {
    const dz = refs.workspaceDropZone;
    if (!dz) return;
    
    dz.addEventListener('dragover', (e) => {
        e.preventDefault();
        dz.classList.add('dragover');
    });
    
    dz.addEventListener('dragleave', () => {
        dz.classList.remove('dragover');
    });
    
    dz.addEventListener('drop', (e) => {
        e.preventDefault();
        dz.classList.remove('dragover');
        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0]);
        }
    });
    
    dz.addEventListener('click', () => {
        if(refs.fileInput) refs.fileInput.click();
    });
    
    refs.fileInput?.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFile(e.target.files[0]);
        }
    });
    
    // Wire up giant glows Run OCR button!
    refs.startBtn?.addEventListener('click', async () => {
        if (!state.selectedFile) return;
        await triggerDocuVerseOCR(state.selectedFile);
    });
}

// 3. Document OCR Execution Flow
async function triggerDocuVerseOCR(file) {
    workspaceState.isProcessing = true;
    if(refs.startBtn) refs.startBtn.disabled = true;
    
    // Show glassmorphic progress overlay inside Visual Viewport
    if(refs.processView) refs.processView.classList.remove('hidden');
    updateProgress("Uploading document...", 0);
    
    // Start stopwatch
    let seconds = 0;
    if(refs.elapsedTime) refs.elapsedTime.innerText = "00:00";
    clearInterval(state.elapsedInterval);
    state.elapsedInterval = setInterval(() => {
        seconds++;
        const mins = String(Math.floor(seconds / 60)).padStart(2, '0');
        const secs = String(seconds % 60).padStart(2, '0');
        if(refs.elapsedTime) refs.elapsedTime.innerText = `${mins}:${secs}`;
    }, 1000);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('client_id', clientId);
    await ensureProgressSession();
    formData.append('progress_channel', state.progressChannelId);
    formData.append('progress_token', state.progressSessionToken);
    
    // Append form parameters
    const settings = getFormSettings();
    Object.entries(settings).forEach(([k, v]) => {
        formData.append(k, v);
    });
    
    try {
        const response = await fetch('/process', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'OCR Processing failed');
        }

        const textArtifactId = response.headers.get('X-Text-Artifact-Id');
        const textArtifactToken = response.headers.get('X-Text-Artifact-Token');
        if (!textArtifactId || !textArtifactToken) {
            throw new Error('OCR completed but text artifact metadata was missing');
        }
        state.currentJobId = textArtifactId;
        state.currentJobToken = textArtifactToken;

        const blob = await response.blob();
        state.resultBlob = blob;
        state.resultFilename = `OCR_${file.name}`;
        
        // Load the parsed searchable PDF back into workspace visualizer!
        const parsedFile = new File([blob], state.resultFilename, { type: 'application/pdf' });
        await loadWorkspaceDocument(parsedFile);
        
        // Retrieve extracted text JSON
        await fetchExtractedText();
        
        showToast('Document OCR completed successfully!', 'success');
    } catch (err) {
        console.error(err);
        showToast(`OCR Error: ${err.message}`, 'error');
    } finally {
        workspaceState.isProcessing = false;
        clearInterval(state.elapsedInterval);
        if(refs.processView) refs.processView.classList.add('hidden');
        if(refs.startBtn) refs.startBtn.disabled = false;
    }
}

async function fetchExtractedText() {
    try {
        if (!state.currentJobId || !state.currentJobToken) throw new Error("Text artifact metadata is not available");
        const textResp = await fetch(`/text/${encodeURIComponent(state.currentJobId)}?t=${Date.now()}`, {
            headers: { Authorization: `Bearer ${state.currentJobToken}` }
        });
        if (!textResp.ok) throw new Error("Could not fetch extracted text JSON");
        
        const textMap = await textResp.json();
        
        // Save to state
        workspaceState.extractedText = textMap;
        
        // Build markdown representation and raw plain text
        let md = "";
        let plain = "";
        for (const [page, lines] of Object.entries(textMap)) {
            md += `## Page ${parseInt(page) + 1}\n\n`;
            md += lines.join('\n\n') + "\n\n";
            
            plain += `--- PAGE ${parseInt(page) + 1} ---\n`;
            plain += lines.join('\n') + "\n\n";
        }
        
        state.rawTextResult = md;
        
        // Populate tabs textareas
        if(refs.mdContent) {
            refs.mdContent['inner' + 'HTML'] = renderMarkdownToHtml(md);
        }
        if(refs.textContent) refs.textContent.value = plain;
        
        // Pre-populate translator content
        if(refs.translatedMarkdownContent) {
            refs.translatedMarkdownContent['inner' + 'HTML'] = "";
        }
        
        // Switch to Tab 1 (Markdown) automatically
        const tabMd = document.getElementById('tab-btn-text');
        if (tabMd) tabMd.click();
        
    } catch (e) {
        showToast("Extracted text is not available yet.", "info");
    }
}

// 4. Server Configuration Settings Modal
function setupSettingsModal() {
    if (!refs.btnOpenSettingsModal) return;
    
    refs.btnOpenSettingsModal.addEventListener('click', () => {
        if(refs.settingsModal) refs.settingsModal.classList.remove('hidden');
    });
    
    const closeModal = () => {
        if(refs.settingsModal) refs.settingsModal.classList.add('hidden');
    };
    
    refs.settingsModalClose?.addEventListener('click', closeModal);
    refs.settingsModalCancel?.addEventListener('click', closeModal);
    
    refs.settingsModalSave?.addEventListener('click', async () => {
        await saveConfig();
        closeModal();
        showToast('Settings saved successfully!', 'success');
        
        // Refresh models list based on new Server endpoint
        const currentModel = refs.modelSelect ? refs.modelSelect.value : null;
        await fetchModels(currentModel);
    });
}

// 5. Right Sidebar AI Workstation Tabs
function setupAIWorkstationTabs() {
    refs.tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active style from all tabs
            refs.tabBtns.forEach(b => b.classList.remove('active'));
            refs.tabPanels.forEach(p => p.classList.remove('active'));
            
            // Activate selected tab
            btn.classList.add('active');
            const targetId = btn.dataset.tab;
            const panel = document.getElementById(targetId);
            if (panel) panel.classList.add('active');
        });
    });
}

// 6. AI Translation & Structured Schema Extraction Events
function setupAIFeatures() {
    // Copy/Download Markdown Tab
    refs.copyMdBtn?.addEventListener('click', () => {
        if (state.rawTextResult && state.rawTextResult.trim()) {
            navigator.clipboard.writeText(state.rawTextResult).then(() => {
                showToast('Markdown copied to clipboard!', 'success');
            });
        }
    });
    
    refs.dlMdBtn?.addEventListener('click', () => {
        if (state.rawTextResult && state.rawTextResult.trim()) {
            downloadBlobFile(state.rawTextResult, 'extracted_document.md', 'text/markdown');
        }
    });
    
    refs.dlMdDocxBtn?.addEventListener('click', () => {
        if (state.rawTextResult && state.rawTextResult.trim()) {
            const baseName = state.selectedFile ? state.selectedFile.name.replace(/\.[^/.]+$/, "") : "extracted_document";
            downloadDocxFile(state.rawTextResult, `${baseName}.docx`);
        }
    });

    // Copy/Download Text Tab
    refs.copyTextBtn?.addEventListener('click', () => {
        if (refs.textContent && refs.textContent.value.trim()) {
            navigator.clipboard.writeText(refs.textContent.value).then(() => {
                showToast('Plain text copied!', 'success');
            });
        }
    });
    
    refs.dlTxtBtn?.addEventListener('click', () => {
        if (refs.textContent && refs.textContent.value.trim()) {
            downloadBlobFile(refs.textContent.value, 'extracted_document.txt', 'text/plain');
        }
    });

    // --- AI Translator triggers ---
    refs.translateBtn?.addEventListener('click', async () => {
        const text = state.rawTextResult || "";
        if (!text.trim()) {
            showToast("No extracted text found. Run OCR first!", "error");
            return;
        }
        
        const lang = refs.translateLangSelect ? refs.translateLangSelect.value : "Spanish";
        
        refs.translateBtn.disabled = true;
        refs.translateBtn.innerText = "Translating...";
        if(refs.translatedMarkdownContent) {
            refs.translatedMarkdownContent['inner' + 'HTML'] = `<span class="text-muted" style="font-style:italic;">AI is translating your document. Please wait...</span>`;
        }
        
        try {
            const translated = await translateText(text, lang);
            state.translatedText = translated;
            if(refs.translatedMarkdownContent) {
                refs.translatedMarkdownContent['inner' + 'HTML'] = renderMarkdownToHtml(translated);
            }
            showToast(`Document translated to ${lang}!`, 'success');
        } catch (e) {
            showToast(`Translation failed: ${e.message}`, 'error');
            if(refs.translatedMarkdownContent) {
                refs.translatedMarkdownContent['inner' + 'HTML'] = `<span class="error-text">Error: ${e.message}</span>`;
            }
        } finally {
            refs.translateBtn.disabled = false;
            refs.translateBtn.innerText = "Translate";
        }
    });

    // Copy / Download Translated text
    refs.copyTransBtn?.addEventListener('click', () => {
        if (state.translatedText && state.translatedText.trim()) {
            navigator.clipboard.writeText(state.translatedText).then(() => {
                showToast('Translation copied!', 'success');
            });
        }
    });
    
    refs.dlTransBtn?.addEventListener('click', () => {
        if (state.translatedText && state.translatedText.trim()) {
            const lang = refs.translateLangSelect ? refs.translateLangSelect.value : "Translated";
            downloadBlobFile(state.translatedText, `translated_${lang.toLowerCase()}.md`, 'text/markdown');
        }
    });
    
    refs.dlTransDocxBtn?.addEventListener('click', () => {
        if (state.translatedText && state.translatedText.trim()) {
            const lang = refs.translateLangSelect ? refs.translateLangSelect.value : "Translated";
            downloadDocxFile(state.translatedText, `translated_${lang.toLowerCase()}.docx`);
        }
    });

    // --- Structured Schema Extractor triggers ---
    refs.extractorTemplateSelect?.addEventListener('change', (e) => {
        // Toggle Custom Prompt field
        if (e.target.value === 'custom') {
            refs.extractorCustomPromptContainer?.classList.remove('hidden');
        } else {
            refs.extractorCustomPromptContainer?.classList.add('hidden');
        }
    });

    refs.extractBtn?.addEventListener('click', async () => {
        const text = state.rawTextResult || "";
        if (!text.trim()) {
            showToast("No extracted text found. Run OCR first!", "error");
            return;
        }
        
        const template = refs.extractorTemplateSelect ? refs.extractorTemplateSelect.value : "invoice";
        const customPrompt = refs.extractorCustomPrompt ? refs.extractorCustomPrompt.value.trim() : "";
        
        refs.extractBtn.disabled = true;
        refs.extractBtn.innerText = "Extracting JSON...";
        if(refs.extractedJsonRaw) refs.extractedJsonRaw.value = "AI is parsing structured fields...";
        renderExtractedJsonStatus('Extracting...');
        
        try {
            const parsedJson = await extractData(text, template, customPrompt);
            state.extractedJson = parsedJson;
            
            // Print raw
            const prettyJson = JSON.stringify(parsedJson, null, 2);
            if(refs.extractedJsonRaw) refs.extractedJsonRaw.value = prettyJson;
            
            // Render visual key-values
            renderExtractedVisualCards(parsedJson);
            
            showToast("Structured fields parsed successfully!", 'success');
        } catch (e) {
            showToast(`Extraction failed: ${e.message}`, 'error');
            if(refs.extractedJsonRaw) refs.extractedJsonRaw.value = `Error: ${e.message}`;
            renderExtractedJsonStatus(`Error: ${e.message}`, { isError: true });
        } finally {
            refs.extractBtn.disabled = false;
            refs.extractBtn.innerText = "Extract Structured Data";
        }
    });

    // Copy / Download JSON text
    refs.copyJsonBtn?.addEventListener('click', () => {
        if (refs.extractedJsonRaw && refs.extractedJsonRaw.value.trim()) {
            navigator.clipboard.writeText(refs.extractedJsonRaw.value).then(() => {
                showToast('JSON copied to clipboard!', 'success');
            });
        }
    });
    
    refs.dlJsonBtn?.addEventListener('click', () => {
        if (refs.extractedJsonRaw && refs.extractedJsonRaw.value.trim()) {
            downloadBlobFile(refs.extractedJsonRaw.value, 'structured_data.json', 'application/json');
        }
    });
}

// 6b. Top-level app shell (Workstation / Translation views)
function switchAppView(viewId) {
    if (!viewId) return;
    refs.appTabBtns.forEach(btn => {
        const isActive = btn.dataset.appView === viewId;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    refs.appViews.forEach(view => {
        const isActive = view.dataset.appView === viewId;
        view.classList.toggle('active', isActive);
        if (isActive) {
            view.removeAttribute('hidden');
        } else {
            view.setAttribute('hidden', '');
        }
    });
    if (window.location.hash !== `#${viewId}`) {
        // Use replaceState to avoid spamming history on every tab click
        try { window.history.replaceState(null, '', `#${viewId}`); } catch (_) {}
    }
}

function setupAppShellTabs() {
    refs.appTabBtns.forEach(btn => {
        btn.addEventListener('click', () => switchAppView(btn.dataset.appView));
    });
    // Reflect #view-* on initial load
    const initial = (window.location.hash || '').replace(/^#/, '');
    if (initial && Array.from(refs.appViews).some(v => v.dataset.appView === initial)) {
        switchAppView(initial);
    } else {
        switchAppView('view-workstation');
    }

    // Workstation Translator "Open in Translation tab" link
    refs.openTranslationTabBtn?.addEventListener('click', () => {
        // Pre-populate the translation source from the latest OCR result
        const sourceText = state.rawTextResult || '';
        if (sourceText.trim() && refs.translationSourceText) {
            refs.translationSourceText.value = sourceText;
        }
        // Mirror the language selection
        if (refs.translateLangSelect && refs.translationTabLangSelect) {
            refs.translationTabLangSelect.value = refs.translateLangSelect.value;
        }
        // Force source mode to paste since we're carrying text
        setTranslationSourceMode('paste');
        switchAppView('view-translation');
    });

    // React to hash changes (e.g. user uses browser back/forward)
    window.addEventListener('hashchange', () => {
        const next = (window.location.hash || '').replace(/^#/, '');
        if (next && Array.from(refs.appViews).some(v => v.dataset.appView === next)) {
            switchAppView(next);
        }
    });
}

// 6c. Dedicated Translation tab logic
function setTranslationSourceMode(mode) {
    refs.translationSourceTabBtns.forEach(btn => {
        const isActive = btn.dataset.sourceMode === mode;
        btn.classList.toggle('active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    if (refs.translationSourcePanePaste) {
        if (mode === 'paste') refs.translationSourcePanePaste.removeAttribute('hidden');
        else refs.translationSourcePanePaste.setAttribute('hidden', '');
    }
    if (refs.translationSourcePaneUpload) {
        if (mode === 'upload') refs.translationSourcePaneUpload.removeAttribute('hidden');
        else refs.translationSourcePaneUpload.setAttribute('hidden', '');
    }
}

function setTranslationOcrProgress(stage, percent) {
    if (!refs.translationOcrProgress) return;
    if (stage === null) {
        refs.translationOcrProgress.classList.add('hidden');
        return;
    }
    refs.translationOcrProgress.classList.remove('hidden');
    if (refs.translationOcrStage) refs.translationOcrStage.textContent = stage;
    const pct = Math.max(0, Math.min(100, percent || 0));
    if (refs.translationOcrPercent) refs.translationOcrPercent.textContent = `${Math.round(pct)}%`;
    if (refs.translationOcrBar) refs.translationOcrBar.style.width = `${pct}%`;
}

function setTranslationFileInfo(file, status) {
    if (!refs.translationFileInfo) return;
    if (file) {
        refs.translationFileInfo.classList.remove('hidden');
        if (refs.translationFileName) refs.translationFileName.textContent = file.name;
        if (refs.translationFileStatus) refs.translationFileStatus.textContent = status || 'Ready';
    } else {
        refs.translationFileInfo.classList.add('hidden');
    }
}

function clearTranslationTab() {
    if (refs.translationSourceText) refs.translationSourceText.value = '';
    if (refs.translationFileInput) refs.translationFileInput.value = '';
    setTranslationFileInfo(null);
    setTranslationOcrProgress(null, 0);
    if (refs.translationTabOutput) {
        refs.translationTabOutput['inner' + 'HTML'] = '';
    }
    state.translationTabResult = '';
}

function getTranslationTabSourceText() {
    // If the upload pane has a file but no extracted text yet, the caller
    // will need to run OCR first; the click handler does that path.
    if (refs.translationSourceText) {
        const t = refs.translationSourceText.value;
        if (t && t.trim()) return t;
    }
    return '';
}

// One-shot: run OCR on the uploaded file, fetch the extracted markdown,
// then immediately translate it into the selected language.
async function runTranslationTabOcrAndTranslate(file, lang) {
    if (!file) return;
    setTranslationFileInfo(file, 'Uploading & OCR…');
    setTranslationOcrProgress('Uploading', 5);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('client_id', clientId);
    await ensureProgressSession();
    formData.append('progress_channel', state.progressChannelId);
    formData.append('progress_token', state.progressSessionToken);

    const settings = getFormSettings();
    Object.entries(settings).forEach(([k, v]) => {
        formData.append(k, v);
    });

    let response;
    try {
        response = await fetch('/process', {
            method: 'POST',
            body: formData
        });
    } catch (e) {
        setTranslationOcrProgress(null, 0);
        setTranslationFileInfo(file, 'Upload failed');
        showToast(`OCR upload failed: ${e.message}`, 'error');
        return;
    }

    if (!response.ok) {
        setTranslationOcrProgress(null, 0);
        setTranslationFileInfo(file, 'OCR failed');
        let errMsg = 'OCR processing failed';
        try { const err = await response.json(); errMsg = err.error || errMsg; } catch (_) {}
        showToast(errMsg, 'error');
        return;
    }

    const artifactId = response.headers.get('X-Text-Artifact-Id');
    const artifactToken = response.headers.get('X-Text-Artifact-Token');
    if (!artifactId || !artifactToken) {
        setTranslationOcrProgress(null, 0);
        setTranslationFileInfo(file, 'Artifact missing');
        showToast('OCR completed but text artifact metadata was missing.', 'error');
        return;
    }

    setTranslationOcrProgress('Extracting text', 60);

    let markdown = '';
    try {
        const textResp = await fetch(`/text/${encodeURIComponent(artifactId)}?t=${Date.now()}`, {
            headers: { Authorization: `Bearer ${artifactToken}` }
        });
        if (!textResp.ok) throw new Error('Could not fetch extracted text');
        const textMap = await textResp.json();
        for (const [page, lines] of Object.entries(textMap)) {
            markdown += `## Page ${parseInt(page) + 1}\n\n`;
            markdown += lines.join('\n\n') + "\n\n";
        }
    } catch (e) {
        setTranslationOcrProgress(null, 0);
        setTranslationFileInfo(file, 'Text fetch failed');
        showToast(`Text fetch failed: ${e.message}`, 'error');
        return;
    }

    if (!markdown.trim()) {
        setTranslationOcrProgress(null, 0);
        setTranslationFileInfo(file, 'No text found');
        showToast('OCR did not return any text. Try a different file or settings.', 'error');
        return;
    }

    // Mirror the OCR'd text into the paste textarea so the user can edit before re-translating
    if (refs.translationSourceText) refs.translationSourceText.value = markdown;

    setTranslationOcrProgress('Translating', 85);
    setTranslationFileInfo(file, 'Translating…');

    try {
        const translated = await translateText(markdown, lang);
        state.translationTabResult = translated;
        if (refs.translationTabOutput) {
            refs.translationTabOutput['inner' + 'HTML'] = renderMarkdownToHtml(translated);
        }
        setTranslationOcrProgress('Done', 100);
        setTranslationFileInfo(file, `Translated to ${lang}`);
        showToast(`Document translated to ${lang}!`, 'success');
    } catch (e) {
        setTranslationOcrProgress(null, 0);
        setTranslationFileInfo(file, 'Translation failed');
        showToast(`Translation failed: ${e.message}`, 'error');
    }
}

function setupTranslationTab() {
    if (!refs.translationTabTranslateBtn) return;

    // Source-mode tab toggle
    refs.translationSourceTabBtns.forEach(btn => {
        btn.addEventListener('click', () => setTranslationSourceMode(btn.dataset.sourceMode));
    });

    // Drop zone -> file input
    if (refs.translationDropZone && refs.translationFileInput) {
        const dz = refs.translationDropZone;
        dz.addEventListener('click', (e) => {
            // Don't double-fire if user clicked the input itself
            if (e.target instanceof HTMLInputElement) return;
            refs.translationFileInput.click();
        });
        ['dragenter', 'dragover'].forEach(evt =>
            dz.addEventListener(evt, e => { e.preventDefault(); dz.classList.add('dragover'); })
        );
        ['dragleave', 'drop'].forEach(evt =>
            dz.addEventListener(evt, e => { e.preventDefault(); dz.classList.remove('dragover'); })
        );
        dz.addEventListener('drop', e => {
            const file = e.dataTransfer?.files?.[0];
            if (file) {
                refs.translationFileInput.files = e.dataTransfer.files;
                setTranslationFileInfo(file, 'Ready');
            }
        });
        refs.translationFileInput.addEventListener('change', e => {
            const file = e.target.files?.[0];
            if (file) setTranslationFileInfo(file, 'Ready');
        });
        refs.translationFileClearBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            refs.translationFileInput.value = '';
            setTranslationFileInfo(null);
            setTranslationOcrProgress(null, 0);
        });
    }

    // Main translate action
    refs.translationTabTranslateBtn.addEventListener('click', async () => {
        const lang = refs.translationTabLangSelect?.value || 'English';
        // If a file is staged, run OCR + translate
        const stagedFile = refs.translationFileInput?.files?.[0];
        if (stagedFile) {
            await runTranslationTabOcrAndTranslate(stagedFile, lang);
            return;
        }
        // Otherwise, translate whatever's in the source textarea
        const text = getTranslationTabSourceText();
        if (!text) {
            showToast('Paste some text or upload a file first.', 'error');
            return;
        }
        refs.translationTabTranslateBtn.disabled = true;
        const originalLabel = refs.translationTabTranslateBtn.innerText;
        refs.translationTabTranslateBtn.innerText = 'Translating…';
        if (refs.translationTabOutput) {
            refs.translationTabOutput['inner' + 'HTML'] =
                '<span class="text-muted" style="font-style:italic;">AI is translating. Please wait…</span>';
        }
        try {
            const translated = await translateText(text, lang);
            state.translationTabResult = translated;
            if (refs.translationTabOutput) {
                refs.translationTabOutput['inner' + 'HTML'] = renderMarkdownToHtml(translated);
            }
            showToast(`Translated to ${lang}!`, 'success');
        } catch (e) {
            if (refs.translationTabOutput) {
                refs.translationTabOutput['inner' + 'HTML'] = `<span class="error-text">Error: ${e.message}</span>`;
            }
            showToast(`Translation failed: ${e.message}`, 'error');
        } finally {
            refs.translationTabTranslateBtn.disabled = false;
            refs.translationTabTranslateBtn.innerText = originalLabel;
        }
    });

    // Copy / download translated output
    refs.translationTabCopyBtn?.addEventListener('click', () => {
        const text = state.translationTabResult;
        if (text && text.trim()) {
            navigator.clipboard.writeText(text).then(() => showToast('Translation copied!', 'success'));
        }
    });
    refs.translationTabDlMdBtn?.addEventListener('click', () => {
        const text = state.translationTabResult;
        if (text && text.trim()) {
            const lang = (refs.translationTabLangSelect?.value || 'Translated').toLowerCase();
            downloadBlobFile(text, `translated_${lang}.md`, 'text/markdown');
        }
    });
    refs.translationTabDlDocxBtn?.addEventListener('click', () => {
        const text = state.translationTabResult;
        if (text && text.trim()) {
            const lang = (refs.translationTabLangSelect?.value || 'Translated').toLowerCase();
            downloadDocxFile(text, `translated_${lang}.docx`);
        }
    });

    refs.translationClearBtn?.addEventListener('click', clearTranslationTab);
}

function renderExtractedVisualCards(json) {
    const grid = refs.extractedJsonVisualCards;
    if (!grid) return;
    grid.replaceChildren();

    // Flat display visualizer
    const entries = Object.entries(json);
    if (entries.length === 0) {
        renderExtractedJsonStatus('Empty schema returned.');
        return;
    }
    
    entries.forEach(([key, val]) => {
        const card = document.createElement('div');
        card.className = 'json-card';
        
        let textVal = "";
        if (typeof val === 'object' && val !== null) {
            textVal = JSON.stringify(val);
        } else {
            textVal = String(val);
        }
        
        // Truncate if long
        if (textVal.length > 150) textVal = textVal.substring(0, 147) + "...";
        
        const keySpan = document.createElement('span');
        keySpan.className = 'json-key';
        keySpan.textContent = key.replace(/_/g, ' ');

        const valueSpan = document.createElement('span');
        valueSpan.className = 'json-val';
        valueSpan.textContent = textVal;

        card.appendChild(keySpan);
        card.appendChild(valueSpan);
        grid.appendChild(card);
    });
}

// 7. General Download Blob helper
function downloadBlob(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

function downloadBlobFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    downloadBlob(blob, filename);
}

// 8. DOCX Exporter Helper
async function downloadDocxFile(text, filename) {
    if (!text || !text.trim()) {
        showToast("No content to export!", "error");
        return;
    }
    try {
        const response = await fetch('/api/export/docx', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        if (!response.ok) {
            throw new Error('Failed to generate DOCX file');
        }
        const blob = await response.blob();
        downloadBlob(blob, filename);
        showToast("DOCX file downloaded successfully!", "success");
    } catch (e) {
        console.error(e);
        showToast(`Export failed: ${e.message}`, "error");
    }
}

// 9. Markdown to HTML Rich Renderer
function renderMarkdownToHtml(markdown) {
    if (!markdown) return '<span class="text-muted" style="font-style:italic;">No content available.</span>';
    
    // Escape HTML to prevent injection and layout bugs
    let escaped = markdown
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
        
    // Split into paragraphs/blocks using double newlines
    let blocks = escaped.split(/\n\n+/);
    let htmlBlocks = [];
    
    for (let block of blocks) {
        block = block.trim();
        if (!block) continue;
        
        // Page break header e.g. ## Page X or --- PAGE X ---
        const pageMatch = block.match(/^(?:##\s+Page\s+(\d+)|---\s+PAGE\s+(\d+)\s+---)$/i);
        if (pageMatch) {
            const pageNum = pageMatch[1] || pageMatch[2];
            htmlBlocks.push(`<div class="rich-page-break"><span class="rich-page-badge">Page ${pageNum}</span></div>`);
            continue;
        }
        
        // Headings
        if (block.startsWith('# ')) {
            htmlBlocks.push(`<h1>${parseInlineMarkdown(block.substring(2))}</h1>`);
            continue;
        }
        if (block.startsWith('## ')) {
            htmlBlocks.push(`<h2>${parseInlineMarkdown(block.substring(3))}</h2>`);
            continue;
        }
        if (block.startsWith('### ')) {
            htmlBlocks.push(`<h3>${parseInlineMarkdown(block.substring(4))}</h3>`);
            continue;
        }
        
        // Bullet Lists
        if (block.startsWith('- ') || block.startsWith('* ')) {
            let items = block.split(/\n[-*]\s+/);
            items[0] = items[0].replace(/^[-*]\s+/, '');
            let listHtml = '<ul>';
            for (let item of items) {
                listHtml += `<li>${parseInlineMarkdown(item.trim())}</li>`;
            }
            listHtml += '</ul>';
            htmlBlocks.push(listHtml);
            continue;
        }
        
        // Numbered Lists
        if (/^\d+\.\s+/.test(block)) {
            let items = block.split(/\n\d+\.\s+/);
            items[0] = items[0].replace(/^\d+\.\s+/, '');
            let listHtml = '<ol>';
            for (let item of items) {
                listHtml += `<li>${parseInlineMarkdown(item.trim())}</li>`;
            }
            listHtml += '</ol>';
            htmlBlocks.push(listHtml);
            continue;
        }
        
        // Regular Paragraph - keep inner single newlines as line breaks
        let paragraphContent = block.split('\n').map(line => parseInlineMarkdown(line.trim())).join('<br>');
        htmlBlocks.push(`<p>${paragraphContent}</p>`);
    }
    
    return htmlBlocks.join('\n');
}

function parseInlineMarkdown(text) {
    // Bold: **text**
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    // Italic: *text* or _text_
    text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
    text = text.replace(/_(.*?)_/g, '<em>$1</em>');
    // Inline code: `code`
    text = text.replace(/`(.*?)`/g, '<code>$1</code>');
    return text;
}
