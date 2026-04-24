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
    postType: 'lifestyle',
    seedImages: [],           // [{mediaId, imageId, url}]
    _tempIdCounter: 0,
    generating: false,
    generationStep: '',
    suggestingTopic: false,
    topicSuggestions: [],

    // ── Preview carousel state ────────────────────────────────────────────
    carouselIndex: 0,
    carouselHover: false,
    captionExpanded: false,

    // ── Image state ───────────────────────────────────────────────────────
    sharedImages: [],        // [{mediaId, imageId, url}]
    deletedShared: [],       // [{mediaId, imageId}] — existing records removed
    platformImages: {},      // {platform: [{mediaId, imageId, url}]}

    // ── Dirty state ───────────────────────────────────────────────────────
    isDirty: false,

    // ── Lifecycle ─────────────────────────────────────────────────────────

    init() {
      // Read publish URL from data attribute (only present for existing posts)
      this.publishUrl = this.$el.dataset.publishUrl || null;

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
      if (postTypeField) {
        this.postType = postTypeField.value || 'lifestyle';
        postTypeField.value = this.postType;
      }

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
          mediaId: this._nextTempId(),
          imageId: item.image_id,
          url: item.url,
        }));
      }

      // Apply prefill from query params (used by inspiration cards)
      const prefillTopicEl = document.getElementById('prefill-topic-json');
      if (prefillTopicEl) {
        this.topic = prefillTopicEl.textContent.trim();
        const topicHidden = document.getElementById('id_topic');
        if (topicHidden) topicHidden.value = this.topic;
      }
      const prefillModeEl = document.getElementById('prefill-mode-json');
      if (prefillModeEl) {
        const prefillMode = prefillModeEl.textContent.trim();
        if (prefillMode === 'ai' || prefillMode === 'editor') {
          this.mode = prefillMode;
        }
      }

      // Track dirty state on any form input/change
      const postForm = document.getElementById('post-form');
      if (postForm) {
        this._dirtyHandler = () => { this.isDirty = true; };
        postForm.addEventListener('input', this._dirtyHandler);
        postForm.addEventListener('change', this._dirtyHandler);
      }

      // Listen for image picker acceptance
      this._pickerHandler = (event) => {
        if (!event.value) return;
        // Image editor result: {imageId, imageUrl}
        if (event.value.imageId && event.value.imageUrl && !event.value.imageIds) {
          this.addEditorResultToSeeds(event.value);
          return;
        }
        // Image picker result: {target, imageIds, urls}
        if (event.value.imageIds) this.pickerAccepted(event.value);
      };
      document.addEventListener('up:layer:accepted', this._pickerHandler);

      this.$nextTick(() => {
        this.syncSharedMediaFormset();
        this.syncPlatformMediaJson();
      });
    },

    destroy() {
      document.removeEventListener('up:layer:accepted', this._pickerHandler);
      const postForm = document.getElementById('post-form');
      if (postForm && this._dirtyHandler) {
        postForm.removeEventListener('input', this._dirtyHandler);
        postForm.removeEventListener('change', this._dirtyHandler);
      }
    },

    // ── Cancel with dirty check ───────────────────────────────────────────

    confirmCancel() {
      if (this.isDirty) {
        if (!confirm('You have unsaved changes. Are you sure you want to cancel?')) {
          return;
        }
      }
      up.layer.dismiss();
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

    // Reset carousel when images change
    _resetCarousel() {
      this.carouselIndex = 0;
    },

    previewTextFormatted() {
      const text = this.effectiveText(this.activeTab);
      if (!text) return '';
      const escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>');
      return escaped
        .replace(/(#\w+)/g, '<span class="text-indigo-500 font-medium">$1</span>')
        .replace(/(@\w+)/g, '<span class="text-sky-500 font-medium">$1</span>');
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
      if (!checked && !this.overrideText[platform]) {
        // Seed override textarea with current shared text as starting point
        this.overrideText[platform] = this.sharedText;
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

    onSharedMediaToggle(platform, event) {
      const checked = event.target.checked;
      if (!checked && !(this.platformImages[platform] && this.platformImages[platform].length)) {
        // Seed platform images with shared images as starting point
        this.platformImages = {
          ...this.platformImages,
          [platform]: this.sharedImages.map(img => ({ mediaId: this._nextTempId(), imageId: img.imageId, url: img.url })),
        };
        this.syncPlatformMediaJson();
      }
      this.overrideMediaShown[platform] = !checked;
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
        if (data.topics && data.topics.length) {
          this.topicSuggestions = data.topics;
        }
      } catch (e) {
        console.error('Failed to suggest topic:', e);
      } finally {
        this.suggestingTopic = false;
      }
    },

    selectTopic(t) {
      this.topic = t;
      this.syncHiddenField('id_topic', t);
      this.topicSuggestions = [];
    },

    // ── AI: Generate Post ─────────────────────────────────────────────────

    async generatePost() {
      if (this.generating) return;
      this.generating = true;
      this.generationStep = 'Generating…';
      try {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;

        this.generationStep = 'Generating your post...';

        // Collect all enabled platforms from hidden platform inputs
        const platforms = [];
        this.$el.querySelectorAll('[name$="-platform"]').forEach(input => {
          if (input.value) platforms.push(input.value);
        });

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
        }

        // Add generated image to shared images
        if (data.image) {
          this.sharedImages = [
            ...this.sharedImages,
            { mediaId: this._nextTempId(), imageId: data.image.id, url: data.image.url },
          ];
          this.syncSharedMediaFormset();
          this._resetCarousel();
        }

        // Switch to editor mode
        this.mode = 'editor';
        this.isDirty = true;
      } catch (e) {
        console.error('Failed to generate post:', e);
      } finally {
        this.generating = false;
        this.generationStep = '';
      }
    },

    // ── Textarea helpers ──────────────────────────────────────────────────

    // Return the textarea element for the given tab (defaults to activeTab).
    getTextarea(platform) {
      const p = platform !== undefined ? platform : this.activeTab;
      if (!p || p === 'all') {
        return this.$root.querySelector('#id_shared_text');
      }
      return this.$root.querySelector(`#panel-${p} .override-text-field`);
    },

    // Update textarea value + reactive state for the given tab.
    updateText(platform, text) {
      const p = platform !== undefined ? platform : this.activeTab;
      const ta = this.getTextarea(p);
      if (ta) ta.value = text;
      if (!p || p === 'all') {
        this.sharedText = text;
      } else {
        this.overrideText = { ...this.overrideText, [p]: text };
      }
    },

    // ── Temp ID helper ────────────────────────────────────────────────────

    _nextTempId() {
      return --this._tempIdCounter;
    },

    // ── Seed Image Management ─────────────────────────────────────────────

    removeSeedImage(mediaId) {
      this.seedImages = this.seedImages.filter(i => i.mediaId !== mediaId);
      this.isDirty = true;
    },

    addEditorResultToSeeds({ imageId, imageUrl }) {
      if (!imageId || this.seedImages.some(i => i.imageId === imageId)) return;
      this.seedImages = [...this.seedImages, { mediaId: this._nextTempId(), imageId, url: imageUrl }];
      this.isDirty = true;
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
      this.isDirty = true;
      if (target === 'seed') {
        // Seed images: replace fully
        this.seedImages = imageIds.map(id => ({
          mediaId: this._nextTempId(),
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
            if (img.mediaId > 0) {
              this.deletedShared = [...this.deletedShared, { mediaId: img.mediaId, imageId: img.imageId }];
            }
            return false;
          }
          return true;
        });
        const existingImageIds = this.sharedImages.map(i => i.imageId);
        imageIds.forEach(id => {
          if (!existingImageIds.includes(id)) {
            newShared.push({ mediaId: this._nextTempId(), imageId: id, url: urls[id] });
          }
        });
        this.sharedImages = newShared;
        this.syncSharedMediaFormset();
        this._resetCarousel();
      } else {
        const platform = target.replace('platform:', '');
        const existing = this.platformImages[platform] || [];
        const existingImageIds = existing.map(i => i.imageId);
        const newList = existing.filter(img => imageIds.includes(img.imageId));
        imageIds.forEach(id => {
          if (!existingImageIds.includes(id)) {
            newList.push({ mediaId: this._nextTempId(), imageId: id, url: urls[id] });
          }
        });
        this.platformImages = { ...this.platformImages, [platform]: newList };
        this.syncPlatformMediaJson();
      }
    },

    // ── Shared image removal ──────────────────────────────────────────────

    removeSharedImage(mediaId) {
      const idx = this.sharedImages.findIndex(i => i.mediaId === mediaId);
      if (idx === -1) return;
      const removed = this.sharedImages[idx];
      this.sharedImages = this.sharedImages.filter((_, i) => i !== idx);
      if (removed.mediaId > 0) {
        this.deletedShared = [...this.deletedShared, { mediaId: removed.mediaId, imageId: removed.imageId }];
      }
      this.carouselIndex = Math.min(this.carouselIndex, Math.max(0, this.sharedImages.length - 1));
      this.syncSharedMediaFormset();
      this.isDirty = true;
    },

    // ── Platform image removal ────────────────────────────────────────────

    removePlatformImage(platform, mediaId) {
      const list = this.platformImages[platform] || [];
      const newList = list.filter(i => i.mediaId !== mediaId);
      this.platformImages = {
        ...this.platformImages,
        [platform]: newList,
      };
      this.carouselIndex = Math.min(this.carouselIndex, Math.max(0, newList.length - 1));
      this.syncPlatformMediaJson();
      this.isDirty = true;
    },

    // ── Formset sync ──────────────────────────────────────────────────────

    syncSharedMediaFormset() {
      const container = document.getElementById('shared-media-inputs');
      if (!container) return;
      container.innerHTML = '';

      const prefix = 'media';
      let formIdx = 0;

      // Active existing images (have a real DB mediaId)
      const existingActive = this.sharedImages.filter(i => i.mediaId > 0);
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

      // New images (temp negative mediaId, not yet saved)
      const newImages = this.sharedImages.filter(i => !(i.mediaId > 0));
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

    // ── Save & Publish state ──────────────────────────────────────────────

    saving: false,
    publishing: false,
    publishResult: null,   // null | { successes: [], failures: {} }
    publishUrl: null,

    // ── Save post ─────────────────────────────────────────────────────────

    async savePost(closeOnSuccess = true, action = 'draft') {
      const form = document.getElementById('post-form');
      if (!form) return;

      this.saving = true;
      try {
        this.syncSharedMediaFormset();
        this.syncPlatformMediaJson();

        await up.submit(form, { params: { action }, layer: 'current', target: ':none' });

        if (closeOnSuccess) {
          up.layer.accept();
        }
      } finally {
        this.saving = false;
      }
    },

    // ── Publish Now ───────────────────────────────────────────────────────

    async publishNow() {
      if (this.publishing || !this.publishUrl) return;
      this.publishing = true;
      this.publishResult = null;

      try {
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
          || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';

        // Step 1: Save current form state (keep modal open)
        await this.savePost(false);

        // Step 2: Publish to connected platforms
        const resp = await fetch(this.publishUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken },
        });
        const data = await resp.json();
        this.publishResult = data;

        // Notify the post list to reload
        up.emit('social_media:changed');

        // Close the modal after a short delay when all platforms succeeded
        if (data.successes && data.successes.length > 0 && Object.keys(data.failures || {}).length === 0) {
          setTimeout(() => up.layer.accept(), 1200);
        }
      } catch (e) {
        console.error('Failed to publish:', e);
        this.publishResult = { successes: [], failures: { general: e.message } };
      } finally {
        this.publishing = false;
      }
    },

  }));
});
