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

    // ── Publish / status state ────────────────────────────────────────────
    postStatus: '',       // mirrors server-side post.status
    scheduledAt: '',      // ISO string of scheduled_at, empty when not scheduled
    postId: null,
    unscheduleUrl: null,

    // ── Lifecycle ─────────────────────────────────────────────────────────

    init() {
      // Read publish URL from data attribute (only present for existing posts)
      this.publishUrl = this.$el.dataset.publishUrl || null;
      this.publishPanelUrl = this.$el.dataset.publishPanelUrl || null;
      this.postId = this.$el.dataset.postId || null;
      this.postStatus = this.$el.dataset.postStatus || '';
      this.scheduledAt = this.$el.dataset.scheduledAt || '';
      this.unscheduleUrl = this.$el.dataset.unscheduleUrl || null;

      // Listen for status changes emitted by the publish panel
      this._statusChangedHandler = (event) => {
        this.postStatus = event.status || '';
        this.scheduledAt = event.scheduledAt || '';
        up.emit('social_media:changed');
      };
      document.addEventListener('social_media:status_changed', this._statusChangedHandler);
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
      document.removeEventListener('social_media:status_changed', this._statusChangedHandler);
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

    // ── Save state ────────────────────────────────────────────────────────

    saving: false,
    publishUrl: null,
    publishPanelUrl: null,

    // ── Drag-and-drop state ───────────────────────────────────────────────
    dragSourceIndex: null,
    dragSourceType: null,
    dragSourcePlatform: null,
    dragOverIndex: null,
    dragOverType: null,

    // Returns human-readable label for current postStatus
    statusLabel() {
      const map = {
        draft: 'Draft',
        scheduled: 'Scheduled',
        publishing: 'Publishing…',
        published: 'Published',
        failed: 'Failed',
      };
      return map[this.postStatus] || this.postStatus;
    },

    // Returns badge label including scheduled date when applicable
    statusBadgeLabel() {
      if (this.postStatus === 'scheduled' && this.scheduledAt) {
        return 'Scheduled · ' + formatScheduledAt(this.scheduledAt);
      }
      return this.statusLabel();
    },
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

    // ── Drag-and-drop image reorder ───────────────────────────────────────

    isDragOver(index, type, platform = null) {
      return this.dragOverIndex === index &&
        this.dragOverType === type + ':' + (platform || '');
    },

    dragStart(e, index, type, platform = null) {
      this.dragSourceIndex = index;
      this.dragSourceType = type;
      this.dragSourcePlatform = platform;
      e.dataTransfer.effectAllowed = 'move';
    },

    dragOver(e, index, type, platform = null) {
      if (this.dragSourceType !== type || this.dragSourcePlatform !== platform) return;
      this.dragOverIndex = index;
      this.dragOverType = type + ':' + (platform || '');
    },

    drop(e, targetIndex, type, platform = null) {
      if (this.dragSourceIndex === null ||
          this.dragSourceType !== type ||
          this.dragSourcePlatform !== platform) return;
      const sourceIdx = this.dragSourceIndex;
      let arr;
      if (type === 'shared') arr = [...this.sharedImages];
      else if (type === 'seed') arr = [...this.seedImages];
      else if (type === 'platform') arr = [...(this.platformImages[platform] || [])];
      else return;
      const [moved] = arr.splice(sourceIdx, 1);
      arr.splice(targetIndex, 0, moved);
      if (type === 'shared') {
        this.sharedImages = arr;
        this.$nextTick(() => this.syncSharedMediaFormset());
      } else if (type === 'seed') {
        this.seedImages = arr;
      } else if (type === 'platform') {
        this.platformImages = { ...this.platformImages, [platform]: arr };
        this.$nextTick(() => this.syncPlatformMediaJson());
      }
      this.dragEnd();
      this._resetCarousel();
    },

    dragEnd() {
      this.dragSourceIndex = null;
      this.dragSourceType = null;
      this.dragSourcePlatform = null;
      this.dragOverIndex = null;
      this.dragOverType = null;
    },

  }));

  // ── Publish Panel ────────────────────────────────────────────────────────

  Alpine.data('publishPanel', () => ({

    // ── State ───────────────────────────────────────────────────────────
    view: 'options',       // 'options' | 'publishing' | 'results'
    postStatus: '',
    scheduledAt: '',
    scheduleError: '',
    scheduling: false,
    unscheduling: false,
    publishing: false,
    liveResults: [],       // [{platform, success, error}] — set after SSE publish-done

    postId: null,
    publishUrl: null,
    scheduleUrl: null,
    unscheduleUrl: null,

    // ── Lifecycle ────────────────────────────────────────────────────────
    init() {
      this.postId        = this.$el.dataset.postId;
      this.postStatus    = this.$el.dataset.postStatus || '';
      // data-scheduled-at is a UTC ISO string (with +00:00 offset); convert to local
      // time for the datetime-local input which always works in browser-local time.
      const rawScheduledAt = this.$el.dataset.scheduledAt || '';
      if (rawScheduledAt) {
        const d = new Date(rawScheduledAt);
        this.scheduledAt = isNaN(d.getTime()) ? rawScheduledAt : toLocalISOString(d);
      }
      this.publishUrl    = this.$el.dataset.publishUrl;
      this.scheduleUrl   = this.$el.dataset.scheduleUrl;
      this.unscheduleUrl = this.$el.dataset.unscheduleUrl;

      // Determine initial view from current post status
      if (this.postStatus === 'published' || this.postStatus === 'failed') {
        this.view = 'results';
      } else if (this.postStatus === 'publishing') {
        this.view = 'publishing';
        this._subscribeSSE();
      } else {
        this.view = 'options';
      }
    },

    // ── Status label ─────────────────────────────────────────────────────
    statusLabel() {
      const map = {
        draft: 'Draft',
        scheduled: 'Scheduled',
        publishing: 'Publishing…',
        published: 'Published',
        failed: 'Failed',
      };
      return map[this.postStatus] || this.postStatus;
    },

    // ── Datetime helpers ──────────────────────────────────────────────────
    minDatetime() {
      const now = new Date();
      now.setMinutes(now.getMinutes() + 1);
      return toLocalISOString(now);
    },

    formatScheduledAt(iso) {
      return formatScheduledAt(iso);
    },

    // ── Schedule ─────────────────────────────────────────────────────────
    async schedulePost() {
      this.scheduleError = '';
      if (!this.scheduledAt) {
        this.scheduleError = 'Please enter a date and time.';
        return;
      }
      const dt = new Date(this.scheduledAt);
      if (isNaN(dt.getTime())) {
        this.scheduleError = 'Invalid date format.';
        return;
      }
      if (dt <= new Date()) {
        this.scheduleError = 'Scheduled time must be in the future.';
        return;
      }

      this.scheduling = true;
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
      try {
        // dt is a local-time Date (parsed from the datetime-local input); send as UTC ISO.
        const body = new URLSearchParams({ scheduled_at: dt.toISOString() });
        const resp = await fetch(this.scheduleUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/x-www-form-urlencoded' },
          body,
        });
        const data = await resp.json();
        if (!resp.ok) {
          this.scheduleError = data.error || 'Failed to schedule.';
          return;
        }
        this.postStatus = data.status;
        // Notify editor of status change, then close only the publish panel
        up.emit('social_media:status_changed', { status: data.status, scheduledAt: data.scheduled_at });
        up.layer.dismiss();
      } catch (e) {
        this.scheduleError = 'Failed to schedule. Please try again.';
      } finally {
        this.scheduling = false;
      }
    },

    // ── Unschedule ────────────────────────────────────────────────────────
    async unschedulePost() {
      this.unscheduling = true;
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
      try {
        const resp = await fetch(this.unscheduleUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken },
        });
        const data = await resp.json();
        this.postStatus = data.status;
        up.emit('social_media:status_changed', { status: 'draft', scheduledAt: '' });
        up.layer.dismiss();
      } catch (e) {
        console.error('Failed to unschedule:', e);
      } finally {
        this.unscheduling = false;
      }
    },

    // ── Publish Now ───────────────────────────────────────────────────────
    async publishNow() {
      if (this.publishing || !this.publishUrl) return;
      this.publishing = true;
      this.view = 'publishing';
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
      try {
        const resp = await fetch(this.publishUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken },
        });
        const data = await resp.json();
        if (data.queued && this.postId) {
          this.postStatus = 'publishing';
          up.emit('social_media:status_changed', { status: 'publishing', scheduledAt: '' });
          this._subscribeSSE();
        } else {
          this.publishing = false;
          this.view = 'options';
        }
      } catch (e) {
        console.error('Failed to publish:', e);
        this.publishing = false;
        this.view = 'options';
      }
    },

    _subscribeSSE() {
      if (!this.postId) return;
      const postId = this.postId;
      let timer = null;

      const handler = (e) => {
        if (e.detail && e.detail.post_id == postId) {
          cleanup();
          this._onPublishDone(e.detail);
        }
      };

      const cleanup = () => {
        document.removeEventListener('publish-done', handler);
        if (timer) { clearTimeout(timer); timer = null; }
      };

      document.addEventListener('publish-done', handler);

      timer = setTimeout(() => {
        cleanup();
        this.publishing = false;
        this.view = 'options';
      }, 6 * 60 * 1000);
    },

    _onPublishDone(data) {
      this.publishing = false;
      this.postStatus = data.status;
      // Build liveResults for display
      const results = [];
      (data.successes || []).forEach(p => results.push({ platform: p, success: true, error: null }));
      Object.entries(data.failures || {}).forEach(([p, err]) => results.push({ platform: p, success: false, error: err }));
      this.liveResults = results;
      this.view = 'results';
      up.emit('social_media:status_changed', { status: data.status, scheduledAt: '' });
      up.emit('social_media:changed');
    },

  }));

});

// ── Shared formatting helpers ─────────────────────────────────────────────────

/**
 * Convert a Date object to a local-time ISO string suitable for datetime-local inputs.
 * Returns "YYYY-MM-DDTHH:mm" in the browser's local timezone (no TZ suffix).
 */
function toLocalISOString(date) {
  const pad = n => String(n).padStart(2, '0');
  return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate())
    + 'T' + pad(date.getHours()) + ':' + pad(date.getMinutes());
}

function formatScheduledAt(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit',
  });
}
