/**
 * Vidgo.AI — Frontend Application Logic
 * Handles uploads, API calls, drag-reorder, AI script generation,
 * transitions, voice preview, background music, progress polling, and social sharing.
 */

document.addEventListener('DOMContentLoaded', () => {
  // ── DOM References ──────────────────────────────────────
  const uploadZone = document.getElementById('upload-zone');
  const fileInput = document.getElementById('file-input');
  const previewGrid = document.getElementById('preview-grid');
  const imageCount = document.getElementById('image-count');
  const clearAllBtn = document.getElementById('clear-all-btn');
  const scriptInput = document.getElementById('script-input');
  const charCount = document.getElementById('char-count');
  const voiceSelect = document.getElementById('voice-select');
  const apiKeyToggle = document.getElementById('api-key-toggle');
  const apiKeySection = document.getElementById('api-key-section');
  const apiKeyInput = document.getElementById('api-key-input');
  const generateBtn = document.getElementById('generate-btn');
  const btnText = document.getElementById('btn-text');
  const btnSpinner = document.getElementById('btn-spinner');
  const btnIcon = document.getElementById('btn-icon');
  const resultSection = document.getElementById('result-section');
  const geminiKeyInput = document.getElementById('gemini-key-input');

  // AI Script
  const aiGenerateBtn = document.getElementById('ai-generate-btn');
  const aiBtnText = document.getElementById('ai-btn-text');
  const aiSpinner = document.getElementById('ai-spinner');
  const toneSelect = document.getElementById('tone-select');

  // Video customization
  const ratioToggle = document.getElementById('ratio-toggle');
  const durationSlider = document.getElementById('duration-slider');
  const durationValue = document.getElementById('duration-value');
  const titleInput = document.getElementById('title-input');
  const titlePosition = document.getElementById('title-position');

  // Transitions
  const transitionGrid = document.getElementById('transition-grid');
  const transitionDurationSlider = document.getElementById('transition-duration-slider');
  const transitionDurationValue = document.getElementById('transition-duration-value');

  // Speed toggle
  const speedToggle = document.getElementById('speed-toggle');

  // Music
  const musicGrid = document.getElementById('music-grid');
  const musicVolumeGroup = document.getElementById('music-volume-group');
  const musicVolumeSlider = document.getElementById('music-volume');
  const volumeValue = document.getElementById('volume-value');

  // Progress
  const progressSection = document.getElementById('progress-section');
  const progressStatus = document.getElementById('progress-status');
  const progressPercent = document.getElementById('progress-percent');
  const progressBarFill = document.getElementById('progress-bar-fill');
  const progressMessage = document.getElementById('progress-message');

  // Voice preview
  const voicePreviewBtn = document.getElementById('voice-preview-btn');
  const previewIcon = document.getElementById('preview-icon');
  const previewSpinner = document.getElementById('preview-spinner');
  const previewAudio = document.getElementById('preview-audio');

  let selectedFiles = [];
  let objectUrls = [];
  let selectedRatio = '9:16';
  let selectedMusic = '';
  let selectedTransition = 'fade';
  let selectedSpeed = 'normal';
  const MAX_IMAGES = 20;
  const MAX_SCRIPT = 5000;

  // ══════════════════════════════════════════════════════════
  //  Voice Loading (Categorized)
  // ══════════════════════════════════════════════════════════

  async function loadVoices() {
    try {
      const apiKey = apiKeyInput ? apiKeyInput.value.trim() : '';
      const res = await fetch('/api/voices', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ api_key: apiKey }),
      });
      const data = await res.json();
      voiceSelect.innerHTML = '';

      // Free voices group
      if (data.free && data.free.length > 0) {
        const freeGroup = document.createElement('optgroup');
        freeGroup.label = '🆓 Free Voices';
        data.free.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.voice_id;
          opt.textContent = v.name;
          freeGroup.appendChild(opt);
        });
        voiceSelect.appendChild(freeGroup);
      }

      // Premium voices group
      if (data.premium && data.premium.length > 0) {
        const premiumGroup = document.createElement('optgroup');
        premiumGroup.label = '⭐ Premium Voices';
        data.premium.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.voice_id;
          opt.textContent = v.name;
          premiumGroup.appendChild(opt);
        });
        voiceSelect.appendChild(premiumGroup);
      }

      // Fallback if API returned old format (flat array)
      if (Array.isArray(data)) {
        data.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.voice_id;
          opt.textContent = v.name;
          voiceSelect.appendChild(opt);
        });
      }

    } catch (err) {
      console.error('Failed to load voices:', err);
    }
  }

  loadVoices();

  // ── Voice Preview ──────────────────────────────────────
  voicePreviewBtn.addEventListener('click', async () => {
    const voiceId = voiceSelect.value;
    if (!voiceId || !voiceId.startsWith('gtts_')) {
      showToast('Voice preview is available for free voices only', 'error');
      return;
    }

    previewIcon.style.display = 'none';
    previewSpinner.style.display = 'inline-block';
    voicePreviewBtn.disabled = true;

    try {
      const res = await fetch('/api/voice-preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_id: voiceId }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Preview failed');
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      previewAudio.src = url;
      previewAudio.play();
      previewAudio.onended = () => URL.revokeObjectURL(url);

    } catch (err) {
      showToast(err.message || 'Failed to preview voice', 'error');
    } finally {
      previewIcon.style.display = 'inline';
      previewSpinner.style.display = 'none';
      voicePreviewBtn.disabled = false;
    }
  });

  // ══════════════════════════════════════════════════════════
  //  Transition Grid Loading
  // ══════════════════════════════════════════════════════════

  async function loadTransitions() {
    try {
      const res = await fetch('/api/transitions');
      const transitions = await res.json();

      transitionGrid.innerHTML = '';
      transitions.forEach((t, i) => {
        const item = document.createElement('div');
        item.className = 'transition-item' + (i === 0 ? ' selected' : '');
        item.dataset.transition = t.id;
        item.innerHTML = `
          <span class="transition-icon">${t.icon}</span>
          <span class="transition-name">${t.label}</span>
          <span class="transition-desc">${t.desc}</span>
        `;
        item.addEventListener('click', () => {
          transitionGrid.querySelectorAll('.transition-item').forEach(el => el.classList.remove('selected'));
          item.classList.add('selected');
          selectedTransition = t.id;
        });
        transitionGrid.appendChild(item);
      });

      if (transitions.length > 0) {
        selectedTransition = transitions[0].id;
      }
    } catch (err) {
      console.error('Failed to load transitions:', err);
      // Fallback
      transitionGrid.innerHTML = '<p style="color: var(--text-muted); font-size: 0.85rem;">Could not load transitions</p>';
    }
  }

  loadTransitions();

  // ── Transition duration slider ─────────────────────────
  transitionDurationSlider.addEventListener('input', () => {
    transitionDurationValue.textContent = `${transitionDurationSlider.value}s`;
  });

  // ══════════════════════════════════════════════════════════
  //  Speed Toggle
  // ══════════════════════════════════════════════════════════

  speedToggle.querySelectorAll('.speed-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      speedToggle.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedSpeed = btn.dataset.speed;
    });
  });

  // ══════════════════════════════════════════════════════════
  //  Music Loading
  // ══════════════════════════════════════════════════════════

  async function loadMusic() {
    try {
      const res = await fetch('/api/music');
      const tracks = await res.json();
      tracks.forEach(track => {
        const item = document.createElement('div');
        item.className = 'music-item';
        item.dataset.music = track.id;
        item.innerHTML = `
          <span class="music-icon">${getCategoryIcon(track.category)}</span>
          <span class="music-name">${track.name}</span>
          <span class="music-category">${track.category}</span>
          ${!track.available ? '<span class="music-unavailable">Coming Soon</span>' : ''}
        `;
        if (!track.available) {
          item.classList.add('disabled');
        }
        item.addEventListener('click', () => {
          if (item.classList.contains('disabled')) return;
          musicGrid.querySelectorAll('.music-item').forEach(m => m.classList.remove('selected'));
          item.classList.add('selected');
          selectedMusic = track.id;
          musicVolumeGroup.style.display = track.id ? 'block' : 'none';
        });
        musicGrid.appendChild(item);
      });
    } catch (err) {
      console.error('Failed to load music:', err);
    }
  }

  function getCategoryIcon(category) {
    const icons = { 'Energetic': '⚡', 'Chill': '🌊', 'Cinematic': '🎬', 'Inspirational': '🌟' };
    return icons[category] || '🎵';
  }

  // No music button
  musicGrid.querySelector('[data-music=""]').addEventListener('click', () => {
    musicGrid.querySelectorAll('.music-item').forEach(m => m.classList.remove('selected'));
    musicGrid.querySelector('[data-music=""]').classList.add('selected');
    selectedMusic = '';
    musicVolumeGroup.style.display = 'none';
  });

  loadMusic();

  // ── Music Volume Slider ─────────────────────────────────
  musicVolumeSlider.addEventListener('input', () => {
    volumeValue.textContent = `${musicVolumeSlider.value}%`;
  });

  // ── API Key Toggle ──────────────────────────────────────
  apiKeyToggle.addEventListener('click', () => {
    apiKeyToggle.classList.toggle('open');
    apiKeySection.classList.toggle('open');
  });

  let apiKeyTimer = null;
  apiKeyInput.addEventListener('input', () => {
    clearTimeout(apiKeyTimer);
    apiKeyTimer = setTimeout(loadVoices, 800);
  });

  // ── Character Count ─────────────────────────────────────
  scriptInput.addEventListener('input', () => {
    const len = scriptInput.value.length;
    charCount.textContent = `${len} / ${MAX_SCRIPT}`;
    charCount.classList.toggle('over-limit', len > MAX_SCRIPT);
  });

  // ── Aspect Ratio Toggle ─────────────────────────────────
  ratioToggle.querySelectorAll('.ratio-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      ratioToggle.querySelectorAll('.ratio-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedRatio = btn.dataset.ratio;
    });
  });

  // ── Duration Slider ─────────────────────────────────────
  durationSlider.addEventListener('input', () => {
    const val = parseFloat(durationSlider.value);
    durationValue.textContent = val === 0 ? 'Auto' : `${val}s`;
  });

  // ── Drag & Drop File Upload ─────────────────────────────
  uploadZone.addEventListener('click', () => fileInput.click());

  ['dragenter', 'dragover'].forEach(evt => {
    uploadZone.addEventListener(evt, e => {
      e.preventDefault();
      uploadZone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    uploadZone.addEventListener(evt, e => {
      e.preventDefault();
      uploadZone.classList.remove('dragover');
    });
  });

  uploadZone.addEventListener('drop', e => {
    addFiles(Array.from(e.dataTransfer.files).filter(isImageFile));
  });

  fileInput.addEventListener('change', () => {
    addFiles(Array.from(fileInput.files).filter(isImageFile));
    fileInput.value = '';
  });

  function isImageFile(file) {
    return /\.(png|jpe?g|webp|bmp|gif)$/i.test(file.name);
  }

  function addFiles(files) {
    const remaining = MAX_IMAGES - selectedFiles.length;
    if (remaining <= 0) {
      showToast(`Maximum ${MAX_IMAGES} images allowed`, 'error');
      return;
    }
    const toAdd = files.slice(0, remaining);
    if (files.length > remaining) {
      showToast(`Only ${remaining} more image(s) can be added`, 'error');
    }
    selectedFiles.push(...toAdd);
    renderPreviews();
  }

  function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderPreviews();
  }

  // ── Clear All ───────────────────────────────────────────
  clearAllBtn.addEventListener('click', e => {
    e.preventDefault();
    e.stopPropagation();
    selectedFiles = [];
    renderPreviews();
  });

  // ── Image Preview Rendering ─────────────────────────────
  function renderPreviews() {
    objectUrls.forEach(url => URL.revokeObjectURL(url));
    objectUrls = [];
    previewGrid.innerHTML = '';

    selectedFiles.forEach((file, i) => {
      const item = document.createElement('div');
      item.className = 'preview-item';
      item.draggable = true;
      item.dataset.index = i;

      const objectUrl = URL.createObjectURL(file);
      objectUrls.push(objectUrl);

      const img = document.createElement('img');
      img.src = objectUrl;
      img.alt = file.name;

      const orderBadge = document.createElement('span');
      orderBadge.className = 'order-badge';
      orderBadge.textContent = i + 1;

      const removeBtn = document.createElement('button');
      removeBtn.className = 'remove-btn';
      removeBtn.innerHTML = '✕';
      removeBtn.title = 'Remove';
      removeBtn.addEventListener('click', e => {
        e.stopPropagation();
        e.preventDefault();
        removeFile(i);
      });

      // Drag-to-reorder handlers
      item.addEventListener('dragstart', e => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', i.toString());
        item.classList.add('dragging');
      });
      item.addEventListener('dragend', () => item.classList.remove('dragging'));
      item.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        item.classList.add('drag-over');
      });
      item.addEventListener('dragleave', () => item.classList.remove('drag-over'));
      item.addEventListener('drop', e => {
        e.preventDefault();
        e.stopPropagation();
        item.classList.remove('drag-over');
        const fromIndex = parseInt(e.dataTransfer.getData('text/plain'));
        const toIndex = i;
        if (fromIndex !== toIndex) {
          const [moved] = selectedFiles.splice(fromIndex, 1);
          selectedFiles.splice(toIndex, 0, moved);
          renderPreviews();
        }
      });

      item.appendChild(img);
      item.appendChild(orderBadge);
      item.appendChild(removeBtn);
      previewGrid.appendChild(item);
    });

    const hasFiles = selectedFiles.length > 0;
    imageCount.textContent = hasFiles ? `${selectedFiles.length} / ${MAX_IMAGES} images` : '';
    clearAllBtn.style.display = hasFiles ? 'inline-flex' : 'none';
  }

  clearAllBtn.style.display = 'none';

  // ── Keyboard Shortcut ──────────────────────────────────
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (!generateBtn.disabled) handleGenerate();
    }
  });

  // ══════════════════════════════════════════════════════════
  //  AI Script Generation
  // ══════════════════════════════════════════════════════════

  aiGenerateBtn.addEventListener('click', handleAIGenerate);

  async function handleAIGenerate() {
    if (selectedFiles.length === 0) {
      showToast('Upload images first to generate a script', 'error');
      return;
    }

    setAILoading(true);

    const formData = new FormData();
    selectedFiles.forEach(f => formData.append('photos', f));
    formData.append('tone', toneSelect.value);

    const geminiKey = geminiKeyInput ? geminiKeyInput.value.trim() : '';
    if (geminiKey) formData.append('gemini_api_key', geminiKey);

    try {
      const res = await fetch('/api/generate-script', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || 'Script generation failed');
      }

      scriptInput.value = data.script;
      scriptInput.dispatchEvent(new Event('input'));
      showToast('AI script generated! ✨', 'success');

    } catch (err) {
      showToast(err.message || 'Failed to generate script', 'error');
    } finally {
      setAILoading(false);
    }
  }

  function setAILoading(on) {
    aiGenerateBtn.disabled = on;
    aiBtnText.textContent = on ? 'Analyzing images...' : 'Generate Script with AI';
    aiSpinner.style.display = on ? 'inline-block' : 'none';
    aiGenerateBtn.querySelector('.btn-ai-icon').style.display = on ? 'none' : 'inline';
  }

  // ══════════════════════════════════════════════════════════
  //  Generate Reel (Async with Polling)
  // ══════════════════════════════════════════════════════════

  generateBtn.addEventListener('click', handleGenerate);

  async function handleGenerate() {
    if (selectedFiles.length === 0) {
      showToast('Please upload at least one image', 'error');
      return;
    }
    if (!scriptInput.value.trim()) {
      showToast('Please enter a narration script', 'error');
      return;
    }
    if (scriptInput.value.length > MAX_SCRIPT) {
      showToast(`Script too long. Max ${MAX_SCRIPT} characters.`, 'error');
      return;
    }

    setLoading(true);
    resultSection.innerHTML = '';
    showProgress(0, 'Submitting job...');

    const formData = new FormData();
    selectedFiles.forEach(f => formData.append('photos', f));
    formData.append('script', scriptInput.value.trim());
    formData.append('voice', voiceSelect.value);
    formData.append('transition', selectedTransition);
    formData.append('transition_duration', transitionDurationSlider.value);
    formData.append('speech_speed', selectedSpeed);
    formData.append('aspect_ratio', selectedRatio);

    const duration = parseFloat(durationSlider.value);
    if (duration > 0) {
      formData.append('duration_per_image', duration.toString());
    }

    const title = titleInput.value.trim();
    if (title) {
      formData.append('title_text', title);
      formData.append('title_position', titlePosition.value);
    }

    if (selectedMusic) {
      formData.append('music', selectedMusic);
      formData.append('music_volume', (parseInt(musicVolumeSlider.value) / 100).toString());
    }

    const apiKey = apiKeyInput.value.trim();
    if (apiKey) formData.append('api_key', apiKey);

    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || 'Generation failed');
      }

      // Start polling for progress
      pollJobStatus(data.job_id);

    } catch (err) {
      showToast(err.message || 'Something went wrong', 'error');
      hideProgress();
      setLoading(false);
    }
  }

  // ── Job Status Polling ──────────────────────────────────
  function pollJobStatus(jobId) {
    const pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/status/${jobId}`);
        const data = await res.json();

        if (!res.ok) {
          clearInterval(pollInterval);
          showToast(data.error || 'Job status check failed', 'error');
          hideProgress();
          setLoading(false);
          return;
        }

        showProgress(data.progress, data.message);

        if (data.status === 'done') {
          clearInterval(pollInterval);
          hideProgress();
          setLoading(false);
          showResult(data.result);
          showToast('Reel generated successfully! 🎬', 'success');
        } else if (data.status === 'error') {
          clearInterval(pollInterval);
          hideProgress();
          setLoading(false);
          showToast(data.error || 'Generation failed', 'error');
        }

      } catch (err) {
        clearInterval(pollInterval);
        hideProgress();
        setLoading(false);
        showToast('Lost connection to server', 'error');
      }
    }, 2000);
  }

  // ── Progress Bar ────────────────────────────────────────
  function showProgress(percent, message) {
    progressSection.style.display = 'block';
    progressBarFill.style.width = `${percent}%`;
    progressPercent.textContent = `${percent}%`;
    progressMessage.textContent = message || 'Processing...';
    progressStatus.textContent = percent < 100 ? 'Processing...' : 'Complete!';
  }

  function hideProgress() {
    progressSection.style.display = 'none';
  }

  function setLoading(on) {
    generateBtn.disabled = on;
    btnText.textContent = on ? 'Generating...' : 'Generate Reel';
    btnSpinner.style.display = on ? 'block' : 'none';
    btnIcon.style.display = on ? 'none' : 'inline';
  }

  // ── Result Display with Social Sharing ──────────────────
  function showResult(data) {
    resultSection.innerHTML = `
      <div class="card result-section">
        <h3 class="card-title"><span class="icon">🎬</span> Your Reel is Ready!</h3>
        <div class="video-wrapper">
          <video controls autoplay src="${data.video_url}"></video>
        </div>
        <div class="result-meta">
          <span class="meta-badge"><span class="icon">📁</span> ${data.video_size_mb} MB</span>
          <span class="meta-badge"><span class="icon">🖼️</span> ${data.num_images} images</span>
          <span class="meta-badge"><span class="icon">🎙️</span> ${data.tts_engine}</span>
        </div>

        <div class="result-actions">
          <a href="${data.download_url}" class="btn-download" download>
            <span>⬇️</span> Download Reel
          </a>
        </div>

        <div class="share-section">
          <h4 class="share-title">📤 Export for Social Media</h4>
          <div class="share-buttons">
            <a href="/api/export/${data.job_id}/instagram" class="share-btn instagram" download>
              <span class="share-icon">📸</span>
              <span class="share-label">Instagram Reels</span>
              <span class="share-sub">1080×1920 · H.264</span>
            </a>
            <a href="/api/export/${data.job_id}/tiktok" class="share-btn tiktok" download>
              <span class="share-icon">🎵</span>
              <span class="share-label">TikTok</span>
              <span class="share-sub">1080×1920 · H.264</span>
            </a>
            <a href="/api/export/${data.job_id}/youtube" class="share-btn youtube" download>
              <span class="share-icon">▶️</span>
              <span class="share-label">YouTube Shorts</span>
              <span class="share-sub">1920×1080 · H.264</span>
            </a>
          </div>
        </div>
      </div>
    `;
    resultSection.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // ── Toast Notifications ─────────────────────────────────
  function showToast(message, type = 'error') {
    document.querySelectorAll('.toast').forEach(t => t.remove());

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${type === 'error' ? '⚠️' : '✅'}</span> ${message}`;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = 'toastOut 0.3s ease forwards';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
});
