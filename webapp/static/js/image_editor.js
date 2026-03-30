/* ── Image Editor Alpine component ── */

document.addEventListener('alpine:init', () => {
  'use strict';

  Alpine.data('imageEditor', () => ({
    // ── State ──────────────────────────────────────────────────────────────
    attachedImages: [],   // [{id, badge, url}]  — images sent to the AI
    nextBadge: 1,
    prompt: '',
    generating: false,
    currentResult: null,   // {id, url, prompt} — most recent generation
    imageHistory: [],      // [{id, url}] — all images used in sessions (inputs + generated), newest first
    generatedHistory: [],  // [{id, url}] — only AI-generated results, newest first
    promptHistory: [],     // [string] — all used prompts, newest first, dedup'd
    groupId: null,
    error: null,

    // ── Lifecycle ──────────────────────────────────────────────────────────

    init() {
      const root = this.$root;
      this._config = {
        pickerUrl: root.dataset.pickerUrl || '',
        generateUrl: root.dataset.generateUrl || '',
      };

      // Pre-load source image if opened in edit mode
      try {
        const src = JSON.parse(root.dataset.sourceImage || 'null');
        if (src && src.id && src.url) {
          this.attachedImages = [{ id: src.id, badge: this.nextBadge++, url: src.url }];
        }
      } catch (_) { /* ignore */ }

      // Listen for image picker acceptance
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

    // ── Picker ─────────────────────────────────────────────────────────────

    openPicker() {
      const selectedIds = this.attachedImages.map(i => i.id).join(',');
      up.layer.open({
        url: `${this._config.pickerUrl}?target=_editor&selected=${selectedIds}`,
        target: '#image-picker',
        mode: 'modal',
        history: false,
        size: 'large',
      });
    },

    pickerAccepted({ imageIds, urls }) {
      const existingIds = new Set(this.attachedImages.map(i => i.id));
      imageIds.forEach(id => {
        if (!existingIds.has(id)) {
          this.attachedImages = [
            ...this.attachedImages,
            { id, badge: this.nextBadge++, url: urls[id] },
          ];
        }
      });
    },

    removeAttachment(id) {
      this.attachedImages = this.attachedImages.filter(i => i.id !== id);
    },

    // ── History actions ────────────────────────────────────────────────────

    // Copy a past prompt into the prompt textarea
    copyPrompt(p) {
      this.prompt = p;
    },

    // Add a previously generated image back into the input area (dedup)
    addFromHistory(img) {
      const existingIds = new Set(this.attachedImages.map(i => i.id));
      if (!existingIds.has(img.id)) {
        this.attachedImages = [
          ...this.attachedImages,
          { id: img.id, badge: this.nextBadge++, url: img.url },
        ];
      }
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
            attachment_ids: this.attachedImages.map(i => i.id),
            group_id: this.groupId,
          }),
        });

        const data = await resp.json();

        if (!resp.ok || data.error) {
          this.error = data.error || 'Generation failed. Please try again.';
          return;
        }

        const img = { id: data.image.id, url: data.image.url };
        this.currentResult = { ...img, prompt: this.prompt };
        this.groupId = data.group_id;

        // Move old input images into quick access (dedup)
        const existingHistoryIds = new Set(this.imageHistory.map(h => h.id));
        const incoming = this.attachedImages
          .filter(i => !existingHistoryIds.has(i.id))
          .map(i => ({ id: i.id, url: i.url }));
        this.imageHistory = [...incoming, ...this.imageHistory];

        // Replace input images with the freshly generated result
        this.attachedImages = [{ id: img.id, badge: 1, url: img.url }];
        this.nextBadge = 2;

        // Add generated image to quick access (dedup)
        if (!this.imageHistory.some(h => h.id === img.id)) {
          this.imageHistory = [img, ...this.imageHistory];
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
      if (!this.currentResult) return;
      up.layer.accept({
        value: {
          imageId: this.currentResult.id,
          imageUrl: this.currentResult.url,
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
