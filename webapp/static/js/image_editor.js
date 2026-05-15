/* ── Image Editor Alpine component ── */

document.addEventListener('alpine:init', () => {
  'use strict';

  Alpine.data('mediaEditor', () => ({
    // ── State ──────────────────────────────────────────────────────────────
    attachedMedia: [],   // [{id, badge, url}]  — media sent to the AI
    nextBadge: 1,
    prompt: '',
    generating: false,
    currentResult: null,   // {id, url, prompt} — most recent generation
    focusMedia: null,      // {id, url} — the main image displayed large in focus
    mediaHistory: [],      // [{id, url}] — all media used in sessions (inputs + generated), newest first
    generatedHistory: [],  // [{id, url}] — only AI-generated results, newest first
    promptHistory: [],     // [string] — all used prompts, newest first, dedup'd
    groupId: null,
    useResult: false,
    error: null,

    // ── Lifecycle ──────────────────────────────────────────────────────────

    init() {
      const root = this.$root;
      this._config = {
        pickerUrl: root.dataset.pickerUrl || '',
        generateUrl: root.dataset.generateUrl || '',
      };

      // Read use_result mode
      this.useResult = root.dataset.useResult === 'true';

      // Pre-load source media into input area (single media edit mode)
      try {
        const src = JSON.parse(root.dataset.sourceMedia || 'null');
        if (src && src.id && src.url) {
          this.attachedMedia = [{ id: src.id, badge: this.nextBadge++, url: src.url }];
          this.focusMedia = { id: src.id, url: src.url };
        }
      } catch (_) { /* ignore */ }

      // Pre-populate Quick Access from group media
      try {
        const quickAccess = JSON.parse(root.dataset.quickAccessMedia || '[]');
        if (Array.isArray(quickAccess) && quickAccess.length > 0) {
          this.mediaHistory = quickAccess
            .filter(img => !img.is_generated)
            .map(img => ({ id: img.id, url: img.url }));
          this.generatedHistory = quickAccess
            .filter(img => img.is_generated)
            .map(img => ({ id: img.id, url: img.url }));
        }
      } catch (_) { /* ignore */ }

      // Pre-load group id so generated media are saved to the same group
      const groupId = root.dataset.groupId;
      if (groupId) this.groupId = parseInt(groupId, 10);

      // Listen for media picker acceptance
      this._pickerHandler = (event) => {
        if (event.value && event.value.target === '_editor') {
          this.pickerAccepted(event.value);
        }
      };
      document.addEventListener('up:layer:accepted', this._pickerHandler);
    },

    destroy() {
      document.removeEventListener('up:layer:accepted', this._pickerHandler);
    },

    // ── Focus ──────────────────────────────────────────────────────────────

    setFocus(img) {
      this.focusMedia = { id: img.id, url: img.url };
    },

    // ── Picker ─────────────────────────────────────────────────────────────

    openPicker() {
      const selectedIds = this.attachedMedia.map(i => i.id).join(',');
      up.layer.open({
        url: `${this._config.pickerUrl}?target=_editor&selected=${selectedIds}`,
        target: '#media-picker',
        mode: 'modal',
        history: false,
        size: 'large',
      });
    },

    pickerAccepted({ mediaIds, urls }) {
      const existingIds = new Set(this.attachedMedia.map(i => i.id));
      mediaIds.forEach(id => {
        if (existingIds.has(id)) return;
        if (this.attachedMedia.length >= 8) return;
        const newItem = { id, badge: this.nextBadge++, url: urls[id] };
        this.attachedMedia = [...this.attachedMedia, newItem];
        // Set as focus if no focus yet
        if (!this.focusMedia) {
          this.focusMedia = { id, url: urls[id] };
        }
      });
    },

    removeAttachment(id) {
      this.attachedMedia = this.attachedMedia.filter(i => i.id !== id);
      // Update focus if removed item was focused
      if (this.focusMedia && this.focusMedia.id === id) {
        if (this.attachedMedia.length > 0) {
          this.focusMedia = { id: this.attachedMedia[0].id, url: this.attachedMedia[0].url };
        } else if (this.currentResult) {
          this.focusMedia = { id: this.currentResult.id, url: this.currentResult.url };
        } else {
          this.focusMedia = null;
        }
      }
    },

    // ── History actions ────────────────────────────────────────────────────

    // Copy a past prompt into the prompt textarea
    copyPrompt(p) {
      this.prompt = p;
    },

    // Add a previously generated media back into the input area (dedup)
    addFromHistory(img) {
      const existingIds = new Set(this.attachedMedia.map(i => i.id));
      if (existingIds.has(img.id)) return;
      if (this.attachedMedia.length >= 8) return;
      this.attachedMedia = [
        ...this.attachedMedia,
        { id: img.id, badge: this.nextBadge++, url: img.url },
      ];
    },

    // ── Generate ───────────────────────────────────────────────────────────

    async generate() {
      if (this.generating || !this.prompt.trim()) return;
      this.generating = true;
      this.error = null;

      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || this._getCsrfFromCookie();

      try {
        const resp = await fetch(this._config.generateUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify({
            prompt: this.prompt,
            attachment_ids: this.attachedMedia.map(i => i.id),
            group_id: this.groupId,
          }),
        });

        const data = await resp.json();

        if (!resp.ok || data.error) {
          this.error = data.error || 'Generation failed. Please try again.';
          return;
        }

        const img = { id: data.media.id, url: data.media.url };
        this.currentResult = { ...img, prompt: this.prompt };
        this.groupId = data.group_id;

        // Move old input media into quick access (dedup)
        const existingHistoryIds = new Set(this.mediaHistory.map(h => h.id));
        const incoming = this.attachedMedia
          .filter(i => !existingHistoryIds.has(i.id))
          .map(i => ({ id: i.id, url: i.url }));
        this.mediaHistory = [...incoming, ...this.mediaHistory];

        // Replace input media with the freshly generated result
        this.attachedMedia = [{ id: img.id, badge: 1, url: img.url }];
        this.nextBadge = 2;

        // Set focus to the generated result
        this.focusMedia = { id: img.id, url: img.url };

        // Add generated media to quick access (dedup)
        if (!this.mediaHistory.some(h => h.id === img.id)) {
          this.mediaHistory = [img, ...this.mediaHistory];
        }

        // Track in generated-only history (dedup)
        if (!this.generatedHistory.some(h => h.id === img.id)) {
          this.generatedHistory = [img, ...this.generatedHistory];
        }

        // Add to prompt history (dedup by content, newest first)
        const p = this.prompt.trim();
        this.promptHistory = [p, ...this.promptHistory.filter(q => q !== p)];

        // Clear the prompt input
        this.prompt = '';

      } catch (e) {
        this.error = 'Network error. Please try again.';
        console.error('Image editor generate error:', e);
      } finally {
        this.generating = false;
      }
    },

    // ── Save / Use result ─────────────────────────────────────────────────

    save() {
      if (!this.focusMedia) return;
      up.layer.accept({
        value: {
          mediaPk: this.focusMedia.id,
          url: this.focusMedia.url,
        },
      });
    },

    // ── Helpers ────────────────────────────────────────────────────────────

    _getCsrfFromCookie() {
      const match = document.cookie.match(/csrftoken=([^;]+)/);
      return match ? match[1] : '';
    },
  }));
});
