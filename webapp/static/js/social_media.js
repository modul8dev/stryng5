/* ── Social Media Post Composer ── */

document.addEventListener('alpine:init', () => {
  'use strict';

  // ── Post Composer ──────────────────────────────────────────────────────

  Alpine.data('postComposer', () => ({
    PLATFORM_LIMITS: {
      linkedin: 3000,
      x: 280,
      facebook: 63206,
      instagram: 2200,
    },

    // ── Mode state ────────────────────────────────────────────────────────
    mode: 'ai',              // 'ai' or 'editor'

    activeTab: 'all',
    sharedText: '',
    overrideTextShown: {},
    overrideMediaShown: {},
    overrideText: {},
    textPrefilled: {},

    // ── AI state ──────────────────────────────────────────────────────────
    topic: '',
    postType: '',
    seedImages: [],           // [{imageId, url}]
    generating: false,
    generationStep: '',
    aiProcessing: false,
    suggestingTopic: false,
    customInstruction: '',

    // ── Image state ───────────────────────────────────────────────────────
    sharedImages: [],        // [{mediaId, imageId, url}]
    deletedShared: [],       // [{mediaId, imageId}] — existing records removed
    platformImages: {},      // {platform: [{mediaId, imageId, url}]}

    // ── Lifecycle ─────────────────────────────────────────────────────────

    init() {
      const ta = this.$el.querySelector('#id_shared_text');
      if (ta) this.sharedText = ta.value;

      // Determine initial mode: existing posts → editor, new → ai
      const isEdit = this.$el.querySelector('[name="seed_images_json"]') !== null
        && document.getElementById('selected-seed-images-json') !== null;
      const hasExistingText = !!(ta && ta.value.trim());

      // Check if this is an edit form (post already exists)
      const postFormAction = document.getElementById('post-form')?.getAttribute('action') || '';
      const editIndicator = this.$el.closest('[x-data]')?.querySelector('h2');
      if (editIndicator && editIndicator.textContent.trim() === 'Edit Post') {
        this.mode = 'editor';
      } else {
        this.mode = 'ai';
      }

      // Load topic and postType from hidden fields
      const topicField = document.getElementById('id_topic');
      if (topicField) this.topic = topicField.value || '';
      const postTypeField = document.getElementById('id_post_type');
      if (postTypeField) this.postType = postTypeField.value || '';

      this.$el.querySelectorAll('[id^="panel-"]:not(#panel-all)').forEach(panel => {
        const platform = panel.id.replace('panel-', '');
        const textToggle = panel.querySelector('.use-shared-text-toggle');
        const mediaToggle = panel.querySelector('.use-shared-media-toggle');
        const overrideField = panel.querySelector('.override-text-field');

        this.overrideTextShown[platform] = textToggle ? !textToggle.checked : false;
        this.overrideMediaShown[platform] = mediaToggle ? !mediaToggle.checked : false;
        this.overrideText[platform] = overrideField ? overrideField.value : '';
        this.textPrefilled[platform] = !!(overrideField && overrideField.value);
      });

      // Load selected shared media
      const sharedEl = document.getElementById('selected-shared-media-json');
      if (sharedEl) {
        const data = JSON.parse(sharedEl.textContent);
        this.sharedImages = data.map(item => ({
          mediaId: item.media_id,
          imageId: item.image_id,
          url: item.url,
        }));
      }

      // Load selected platform override media
      const platformEl = document.getElementById('selected-platform-media-json');
      if (platformEl) {
        const data = JSON.parse(platformEl.textContent);
        this.platformImages = {};
        for (const [platform, images] of Object.entries(data)) {
          this.platformImages[platform] = images.map(item => ({
            mediaId: item.media_id,
            imageId: item.image_id,
            url: item.url,
          }));
        }
      }

      // Load seed images
      const seedEl = document.getElementById('selected-seed-images-json');
      if (seedEl) {
        const data = JSON.parse(seedEl.textContent);
        this.seedImages = data.map(item => ({
          imageId: item.image_id,
          url: item.url,
        }));
      }

      // Listen for image picker acceptance
      this._pickerHandler = (event) => {
        if (event.value) this.pickerAccepted(event.value);
      };
      document.addEventListener('up:layer:accepted', this._pickerHandler);

      this.$nextTick(() => {
        this.syncSharedMediaFormset();
        this.syncPlatformMediaJson();
      });
    },

    destroy() {
      document.removeEventListener('up:layer:accepted', this._pickerHandler);
    },

    // ── Mode switching ────────────────────────────────────────────────────

    switchMode(newMode) {
      this.mode = newMode;
    },

    // ── Hidden field sync ─────────────────────────────────────────────────

    syncHiddenField(fieldId, value) {
      const el = document.getElementById(fieldId);
      if (el) el.value = value;
    },

    // ── Tab management ────────────────────────────────────────────────────

    activateTab(tab) {
      this.activeTab = tab;
    },

    // ── Preview ───────────────────────────────────────────────────────────

    previewLabel() {
      if (this.activeTab === 'all') return 'All Platforms';
      const btn = this.$el.querySelector(`.tab-btn[data-tab="${this.activeTab}"]`);
      return btn ? btn.textContent.trim() : this.activeTab;
    },

    previewText() {
      const text = this.effectiveText(this.activeTab);
      return text || 'Write something above to see a preview\u2026';
    },

    previewImages() {
      if (this.activeTab === 'all') return this.sharedImages;
      const platform = this.activeTab;
      if (this.overrideMediaShown[platform]) {
        return this.platformImages[platform] || [];
      }
      return this.sharedImages;
    },

    // ── Text helpers ──────────────────────────────────────────────────────

    effectiveText(platform) {
      if (!platform || platform === 'all') return this.sharedText;
      if (this.overrideTextShown[platform]) return this.overrideText[platform] || '';
      return this.sharedText;
    },

    sharedCharCountLabel() {
      return this.sharedText.length + ' characters';
    },

    // ── Character counting ────────────────────────────────────────────────

    charCount(platform) {
      return this.effectiveText(platform).length;
    },

    charCountLabel(platform) {
      const limit = this.PLATFORM_LIMITS[platform] || 0;
      return this.charCount(platform) + ' / ' + limit;
    },

    charBarWidth(platform) {
      const count = this.charCount(platform);
      const limit = this.PLATFORM_LIMITS[platform] || 1;
      return Math.min((count / limit) * 100, 100) + '%';
    },

    charBarClass(platform) {
      const count = this.charCount(platform);
      const limit = this.PLATFORM_LIMITS[platform] || 0;
      if (count > limit) return 'bg-red-500';
      if (count > limit * 0.8) return 'bg-amber-400';
      return 'bg-emerald-400';
    },

    isOverLimit(platform) {
      const limit = this.PLATFORM_LIMITS[platform] || 0;
      return this.charCount(platform) > limit;
    },

    overLimitBy(platform) {
      const limit = this.PLATFORM_LIMITS[platform] || 0;
      return this.charCount(platform) - limit;
    },

    // ── Override text toggle ──────────────────────────────────────────────

    onSharedTextToggle(platform, event) {
      const checked = event.target.checked;
      if (!checked && !this.textPrefilled[platform] && !this.overrideText[platform]) {
        this.overrideText[platform] = this.sharedText;
        this.textPrefilled[platform] = true;
        this.$nextTick(() => {
          const panel = this.$el.querySelector('#panel-' + platform);
          if (panel) {
            const field = panel.querySelector('.override-text-field');
            if (field) field.value = this.overrideText[platform];
          }
        });
      }
      this.overrideTextShown[platform] = !checked;
    },

    // ── AI: Suggest Topic ─────────────────────────────────────────────────

    async suggestTopic() {
      if (this.suggestingTopic) return;
      this.suggestingTopic = true;
      try {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        const resp = await fetch('/social-media/ai/suggest-topic/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify({
            seed_image_ids: this.seedImages.map(i => i.imageId),
          }),
        });
        const data = await resp.json();
        if (data.topic) {
          this.topic = data.topic;
          this.syncHiddenField('id_topic', this.topic);
        }
      } catch (e) {
        console.error('Failed to suggest topic:', e);
      } finally {
        this.suggestingTopic = false;
      }
    },

    // ── AI: Generate Post ─────────────────────────────────────────────────

    async generatePost() {
      if (this.generating) return;
      this.generating = true;
      this.generationStep = 'Generating text…';
      try {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        // Collect enabled platforms from the form
        const platformCheckboxes = this.$el.querySelectorAll('[name$="-is_enabled"]');
        const platforms = [];
        this.$el.querySelectorAll('[name$="-platform"]').forEach((input, idx) => {
          const checkbox = platformCheckboxes[idx];
          if (checkbox && checkbox.checked) {
            platforms.push(input.value);
          }
        });

        this.generationStep = 'Generating text & image…';
        const resp = await fetch('/social-media/ai/generate/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify({
            topic: this.topic,
            post_type: this.postType,
            seed_image_ids: this.seedImages.map(i => i.imageId),
            platforms: platforms,
          }),
        });
        const data = await resp.json();

        if (data.error) {
          console.error('Generation error:', data.error);
          return;
        }

        // Populate text
        if (data.text) {
          this.sharedText = data.text;
          const ta = this.$el.querySelector('#id_shared_text');
          if (ta) ta.value = data.text;
        }

        // Add generated image to shared images
        if (data.image) {
          this.sharedImages = [
            ...this.sharedImages,
            { mediaId: null, imageId: data.image.id, url: data.image.url },
          ];
          this.syncSharedMediaFormset();
        }

        // Switch to editor mode
        this.mode = 'editor';
      } catch (e) {
        console.error('Failed to generate post:', e);
      } finally {
        this.generating = false;
        this.generationStep = '';
      }
    },

    // ── AI: Edit Action ───────────────────────────────────────────────────

    async aiEditAction(action) {
      const ta = this.$el.querySelector('#id_shared_text');
      if (!ta) return;

      const text = ta.selectionStart !== ta.selectionEnd
        ? ta.value.substring(ta.selectionStart, ta.selectionEnd)
        : ta.value;

      if (!text.trim()) return;

      this.aiProcessing = true;
      try {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        const resp = await fetch('/social-media/ai/edit-text/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify({
            action: action,
            text: text,
            platform: this.activeTab !== 'all' ? this.activeTab : undefined,
          }),
        });
        const data = await resp.json();
        if (data.text) {
          if (ta.selectionStart !== ta.selectionEnd) {
            // Replace selection
            const before = ta.value.substring(0, ta.selectionStart);
            const after = ta.value.substring(ta.selectionEnd);
            ta.value = before + data.text + after;
          } else {
            ta.value = data.text;
          }
          this.sharedText = ta.value;
        }
      } catch (e) {
        console.error('Failed to edit text:', e);
      } finally {
        this.aiProcessing = false;
      }
    },

    // ── AI: Custom Instruction ────────────────────────────────────────────

    async aiCustomInstruction(insertMode) {
      const ta = this.$el.querySelector('#id_shared_text');
      if (!ta || !this.customInstruction.trim()) return;

      const text = ta.value;
      if (!text.trim() && insertMode === 'replace') return;

      this.aiProcessing = true;
      try {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        const resp = await fetch('/social-media/ai/edit-text/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken,
          },
          body: JSON.stringify({
            action: 'freeform',
            text: text || '(empty post)',
            instruction: this.customInstruction,
          }),
        });
        const data = await resp.json();
        if (data.text) {
          if (insertMode === 'replace') {
            ta.value = data.text;
          } else if (insertMode === 'insert') {
            const pos = ta.selectionStart;
            ta.value = ta.value.substring(0, pos) + data.text + ta.value.substring(pos);
          } else if (insertMode === 'append') {
            ta.value = ta.value + (ta.value ? '\n\n' : '') + data.text;
          }
          this.sharedText = ta.value;
          this.customInstruction = '';
        }
      } catch (e) {
        console.error('Failed to apply custom instruction:', e);
      } finally {
        this.aiProcessing = false;
      }
    },

    // ── Seed Image Management ─────────────────────────────────────────────

    removeSeedImage(imageId) {
      this.seedImages = this.seedImages.filter(i => i.imageId !== imageId);
    },

    // ── Image Picker (Unpoly modal) ───────────────────────────────────────

    openPicker(target) {
      let currentImages;
      if (target === 'seed') {
        currentImages = this.seedImages;
      } else if (target === 'shared') {
        currentImages = this.sharedImages;
      } else {
        currentImages = this.platformImages[target.replace('platform:', '')] || [];
      }
      const selectedIds = currentImages.map(i => i.imageId).join(',');
      up.layer.open({
        url: `/media-library/image-picker/?target=${encodeURIComponent(target)}&selected=${selectedIds}`,
        target: '#image-picker',
        mode: 'modal',
        history: false,
        size: 'large',
      });
    },

    pickerAccepted({ target, imageIds, urls }) {
      if (target === 'seed') {
        // Seed images: replace fully
        this.seedImages = imageIds.map(id => ({
          imageId: id,
          url: urls[id],
        }));
        // Auto-suggest topic when seed images change
        if (this.seedImages.length > 0 && !this.topic) {
          this.suggestTopic();
        }
        return;
      }

      if (target === 'shared') {
        const newShared = this.sharedImages.filter(img => {
          if (!imageIds.includes(img.imageId)) {
            if (img.mediaId) {
              this.deletedShared = [...this.deletedShared, { mediaId: img.mediaId, imageId: img.imageId }];
            }
            return false;
          }
          return true;
        });
        const existingImageIds = this.sharedImages.map(i => i.imageId);
        imageIds.forEach(id => {
          if (!existingImageIds.includes(id)) {
            newShared.push({ mediaId: null, imageId: id, url: urls[id] });
          }
        });
        this.sharedImages = newShared;
        this.syncSharedMediaFormset();
      } else {
        const platform = target.replace('platform:', '');
        const existing = this.platformImages[platform] || [];
        const existingImageIds = existing.map(i => i.imageId);
        const newList = existing.filter(img => imageIds.includes(img.imageId));
        imageIds.forEach(id => {
          if (!existingImageIds.includes(id)) {
            newList.push({ mediaId: null, imageId: id, url: urls[id] });
          }
        });
        this.platformImages = { ...this.platformImages, [platform]: newList };
        this.syncPlatformMediaJson();
      }
    },

    // ── Shared image removal ──────────────────────────────────────────────

    removeSharedImage(imageId) {
      const idx = this.sharedImages.findIndex(i => i.imageId === imageId);
      if (idx === -1) return;
      const removed = this.sharedImages[idx];
      this.sharedImages = this.sharedImages.filter((_, i) => i !== idx);
      if (removed.mediaId) {
        this.deletedShared = [...this.deletedShared, { mediaId: removed.mediaId, imageId: removed.imageId }];
      }
      this.syncSharedMediaFormset();
    },

    // ── Platform image removal ────────────────────────────────────────────

    removePlatformImage(platform, imageId) {
      const list = this.platformImages[platform] || [];
      this.platformImages = {
        ...this.platformImages,
        [platform]: list.filter(i => i.imageId !== imageId),
      };
      this.syncPlatformMediaJson();
    },

    // ── Formset sync ──────────────────────────────────────────────────────

    syncSharedMediaFormset() {
      const container = document.getElementById('shared-media-inputs');
      if (!container) return;
      container.innerHTML = '';

      const prefix = 'media';
      let formIdx = 0;

      // Active existing images (have a mediaId)
      const existingActive = this.sharedImages.filter(i => i.mediaId);
      existingActive.forEach(img => {
        this._appendInput(container, `${prefix}-${formIdx}-id`, img.mediaId);
        this._appendInput(container, `${prefix}-${formIdx}-image`, img.imageId);
        this._appendInput(container, `${prefix}-${formIdx}-sort_order`, formIdx);
        formIdx++;
      });

      // Deleted existing images (marked for deletion)
      this.deletedShared.forEach(item => {
        this._appendInput(container, `${prefix}-${formIdx}-id`, item.mediaId);
        this._appendInput(container, `${prefix}-${formIdx}-image`, item.imageId);
        this._appendInput(container, `${prefix}-${formIdx}-sort_order`, formIdx);
        this._appendInput(container, `${prefix}-${formIdx}-DELETE`, 'on');
        formIdx++;
      });

      const initialCount = existingActive.length + this.deletedShared.length;

      // New images (no mediaId yet)
      const newImages = this.sharedImages.filter(i => !i.mediaId);
      newImages.forEach(img => {
        this._appendInput(container, `${prefix}-${formIdx}-image`, img.imageId);
        this._appendInput(container, `${prefix}-${formIdx}-sort_order`, formIdx);
        formIdx++;
      });

      // Update management form
      const totalInput = document.querySelector(`[name="${prefix}-TOTAL_FORMS"]`);
      if (totalInput) totalInput.value = formIdx;
      const initialInput = document.querySelector(`[name="${prefix}-INITIAL_FORM_COUNT"]`);
      if (initialInput) initialInput.value = initialCount;
    },

    syncPlatformMediaJson() {
      const result = {};
      for (const [platform, images] of Object.entries(this.platformImages)) {
        result[platform] = images.map(img => ({ image_id: img.imageId }));
      }
      const input = document.getElementById('platform-override-media-json-input');
      if (input) input.value = JSON.stringify(result);
    },

    _appendInput(container, name, value) {
      const el = document.createElement('input');
      el.type = 'hidden';
      el.name = name;
      el.value = value;
      container.appendChild(el);
    },
  }));
});
