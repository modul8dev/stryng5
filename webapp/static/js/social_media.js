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
    seedMedia: [],           // [{mediaId, media, url}]
    _tempIdCounter: 0,
    generating: false,
    generationStep: '',
    suggestingTopic: false,
    topicSuggestions: [],
    _generationSseCleanup: null,

    // ── Preview carousel state ────────────────────────────────────────────
    carouselIndex: 0,
    carouselHover: false,
    captionExpanded: false,

    // ── Image state ───────────────────────────────────────────────────────
    sharedMedia: [],        // [{mediaId, media, url}]
    deletedShared: [],       // [{mediaId, media}] — existing records removed
    platformMedia: {},      // {platform: [{mediaId, media, url}]}

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
      this._subscribeGenerationSSE();

      // If post is currently generating, resume SSE listener
      const processingStatus = this.$el.dataset.processingStatus || '';
      if (processingStatus === 'generating') {
        this.generating = true;
        this.generationStep = 'Generating your post...';
      }

      // Listen for post-changed SSE to keep the status badge in sync
      this._postChangedHandler = (e) => {
        if (e.detail && e.detail.post_id == this.postId) {
          this.postStatus = e.detail.status || this.postStatus;
          if (e.detail.scheduled_at !== undefined) {
            this.scheduledAt = e.detail.scheduled_at || '';
          }
        }
      };
      document.addEventListener('post-changed', this._postChangedHandler);
      const ta = this.$el.querySelector('#id_shared_text');
      if (ta) this.sharedText = ta.value;

      // Determine initial mode: existing posts → editor, new → ai
      const isEdit = this.$el.querySelector('[name="seed_media_json"]') !== null
        && document.getElementById('selected-seed-media-json') !== null;
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
        this.sharedMedia = data.map(item => ({
          mediaId: item.media_id,
          media: item.media,
          url: item.url,
          is_video: item.is_video || false,
        }));
      }

      // Load selected platform override media
      const platformEl = document.getElementById('selected-platform-media-json');
      if (platformEl) {
        const data = JSON.parse(platformEl.textContent);
        this.platformMedia = {};
        for (const [platform, media] of Object.entries(data)) {
          this.platformMedia[platform] = media.map(item => ({
            mediaId: item.media_id,
            media: item.media,
            url: item.url,
            is_video: item.is_video || false,
          }));
        }
      }

      // Load seed media
      const seedEl = document.getElementById('selected-seed-media-json');
      if (seedEl) {
        const data = JSON.parse(seedEl.textContent);
        this.seedMedia = data.slice(0, 8).map(item => ({
          mediaId: this._nextTempId(),
          media: item.media,
          url: item.url,
          is_video: item.is_video || false,
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

      // Auto-trigger AI suggest when opened from catalog
      const autoSuggestEl = document.getElementById('prefill-auto-suggest-json');
      if (autoSuggestEl && this.seedMedia.length > 0 && !this.topic) {
        this.$nextTick(() => this.suggestTopic());
      }

      // Track dirty state on any form input/change
      const postForm = document.getElementById('post-form');
      if (postForm) {
        this._dirtyHandler = () => { this.isDirty = true; };
        postForm.addEventListener('input', this._dirtyHandler);
        postForm.addEventListener('change', this._dirtyHandler);
      }

      // Listen for media picker acceptance
      this._pickerHandler = (event) => {
        if (!event.value) return;
        // Image editor result: {media, media}
        if (event.value.media && event.value.media && !event.value.mediaIds) {
          this.addEditorResultToSeeds(event.value);
          return;
        }
        // Image picker result: {target, mediaIds, urls}
        if (event.value.mediaIds) this.pickerAccepted(event.value);
      };
      document.addEventListener('up:layer:accepted', this._pickerHandler);

      this.$nextTick(() => {
        this.syncSharedMediaFormset();
        this.syncPlatformMediaJson();
      });
    },

    destroy() {
      document.removeEventListener('up:layer:accepted', this._pickerHandler);
      document.removeEventListener('post-changed', this._postChangedHandler);
      if (this._generationSseCleanup) this._generationSseCleanup();
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

    previewMedia() {
      if (this.activeTab === 'all') return this.sharedMedia;
      const platform = this.activeTab;
      if (this.overrideMediaShown[platform]) {
        return this.platformMedia[platform] || [];
      }
      return this.sharedMedia;
    },

    // Reset carousel when media change
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
      if (!checked && !(this.platformMedia[platform] && this.platformMedia[platform].length)) {
        // Seed platform media with shared media as starting point
        this.platformMedia = {
          ...this.platformMedia,
          [platform]: this.sharedMedia.map(img => ({ mediaId: this._nextTempId(), media: img.media, url: img.url })),
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
            seed_media_ids: this.seedMedia.map(i => i.media),
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
      this.generationStep = 'Generating your post...';
      try {
        await this.savePost(false, 'generate');
      } catch (e) {
        console.error('Failed to generate post:', e);
        this.generating = false;
        this.generationStep = '';
      }
    },

    _subscribeGenerationSSE() {
      if (this._generationSseCleanup) this._generationSseCleanup();

      let timer = null;

      const handler = (e) => {
        if (e.detail && e.detail.post_id == this.postId) {
          cleanup();
          this._onGenerationDone(e.detail);
        }
      };

      const cleanup = () => {
        document.removeEventListener('generation-done', handler);
        if (timer) { clearTimeout(timer); timer = null; }
        this._generationSseCleanup = null;
      };

      document.addEventListener('generation-done', handler);
      this._generationSseCleanup = cleanup;

      // Safety timeout: give up after 5 minutes
      timer = setTimeout(() => {
        cleanup();
        this.generating = false;
        this.generationStep = '';
      }, 5 * 60 * 1000);
    },

    _onGenerationDone(data) {
      if (data.processing_status === 'completed' && data.post_id) {
        up.navigate('#post-composer', {
          url: `/social-media/${data.post_id}/edit/`,
          layer: 'current',
          history: false,
        });
      }
    },

    closeWhileGenerating() {
      up.layer.dismiss();
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
      this.seedMedia = this.seedMedia.filter(i => i.mediaId !== mediaId);
      this.isDirty = true;
    },

    addEditorResultToSeeds({ media }) {
      if (!media || this.seedMedia.some(i => i.media === media)) return;
      if (this.seedMedia.length >= 8) return;
      this.seedMedia = [...this.seedMedia, { mediaId: this._nextTempId(), media, url: media }];
      this.isDirty = true;
    },

    // ── Image Picker (Unpoly modal) ───────────────────────────────────────

    openPicker(target) {
      let currentMedia;
      if (target === 'seed') {
        currentMedia = this.seedMedia;
      } else if (target === 'shared') {
        currentMedia = this.sharedMedia;
      } else {
        currentMedia = this.platformMedia[target.replace('platform:', '')] || [];
      }
      const selectedIds = currentMedia.map(i => i.media).join(',');
      const allowVideo = target !== 'seed';
      up.layer.open({
        url: `/media-library/media-picker/?target=${encodeURIComponent(target)}&selected=${selectedIds}&allow_video=${allowVideo ? '1' : '0'}`,
        target: '#media-picker',
        mode: 'modal',
        history: false,
        size: 'large',
      });
    },

    pickerAccepted({ target, mediaIds, urls, isVideoMap }) {
      this.isDirty = true;
      if (target === 'seed') {
        // Seed media: replace fully, limit to 8
        this.seedMedia = mediaIds.slice(0, 8).map(id => ({
          mediaId: this._nextTempId(),
          media: id,
          url: urls[id],
          is_video: (isVideoMap && isVideoMap[id]) || false,
        }));
        // Auto-suggest topic when seed media change
        if (this.seedMedia.length > 0 && !this.topic) {
          this.suggestTopic();
        }
        return;
      }

      if (target === 'shared') {
        const newShared = this.sharedMedia.filter(img => {
          if (!mediaIds.includes(img.media)) {
            if (img.mediaId > 0) {
              this.deletedShared = [...this.deletedShared, { mediaId: img.mediaId, media: img.media }];
            }
            return false;
          }
          return true;
        });
        const existingImageIds = this.sharedMedia.map(i => i.media);
        mediaIds.forEach(id => {
          if (!existingImageIds.includes(id)) {
            newShared.push({ mediaId: this._nextTempId(), media: id, url: urls[id], is_video: (isVideoMap && isVideoMap[id]) || false });
          }
        });
        this.sharedMedia = newShared;
        this.syncSharedMediaFormset();
        this._resetCarousel();
      } else {
        const platform = target.replace('platform:', '');
        const existing = this.platformMedia[platform] || [];
        const existingImageIds = existing.map(i => i.media);
        const newList = existing.filter(img => mediaIds.includes(img.media));
        mediaIds.forEach(id => {
          if (!existingImageIds.includes(id)) {
            newList.push({ mediaId: this._nextTempId(), media: id, url: urls[id], is_video: (isVideoMap && isVideoMap[id]) || false });
          }
        });
        this.platformMedia = { ...this.platformMedia, [platform]: newList };
        this.syncPlatformMediaJson();
      }
    },

    // ── Shared media removal ──────────────────────────────────────────────

    removeSharedImage(mediaId) {
      const idx = this.sharedMedia.findIndex(i => i.mediaId === mediaId);
      if (idx === -1) return;
      const removed = this.sharedMedia[idx];
      this.sharedMedia = this.sharedMedia.filter((_, i) => i !== idx);
      if (removed.mediaId > 0) {
        this.deletedShared = [...this.deletedShared, { mediaId: removed.mediaId, media: removed.media }];
      }
      this.carouselIndex = Math.min(this.carouselIndex, Math.max(0, this.sharedMedia.length - 1));
      this.syncSharedMediaFormset();
      this.isDirty = true;
    },

    // ── Platform media removal ────────────────────────────────────────────

    removePlatformImage(platform, mediaId) {
      const list = this.platformMedia[platform] || [];
      const newList = list.filter(i => i.mediaId !== mediaId);
      this.platformMedia = {
        ...this.platformMedia,
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

      // Active existing media (have a real DB mediaId)
      const existingActive = this.sharedMedia.filter(i => i.mediaId > 0);
      existingActive.forEach(img => {
        this._appendInput(container, `${prefix}-${formIdx}-id`, img.mediaId);
        this._appendInput(container, `${prefix}-${formIdx}-media`, img.media);
        this._appendInput(container, `${prefix}-${formIdx}-sort_order`, formIdx);
        formIdx++;
      });

      // Deleted existing media (marked for deletion)
      this.deletedShared.forEach(item => {
        this._appendInput(container, `${prefix}-${formIdx}-id`, item.mediaId);
        this._appendInput(container, `${prefix}-${formIdx}-media`, item.media);
        this._appendInput(container, `${prefix}-${formIdx}-sort_order`, formIdx);
        this._appendInput(container, `${prefix}-${formIdx}-DELETE`, 'on');
        formIdx++;
      });

      const initialCount = existingActive.length + this.deletedShared.length;

      // New media (temp negative mediaId, not yet saved)
      const newMedia = this.sharedMedia.filter(i => !(i.mediaId > 0));
      newMedia.forEach(img => {
        this._appendInput(container, `${prefix}-${formIdx}-media`, img.media);
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
      for (const [platform, media] of Object.entries(this.platformMedia)) {
        result[platform] = media.map(img => ({ media: img.media }));
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

    // ── Publish validation ────────────────────────────────────────────────

    /**
     * Validate media constraints for every active platform.
     * Returns an array of human-readable error strings (empty = valid).
     */
    validateForPublish() {
      const PLATFORM_LABELS = {
        linkedin: 'LinkedIn',
        x: 'X (Twitter)',
        facebook: 'Facebook',
        instagram: 'Instagram',
      };

      const errors = [];
      this.$el.querySelectorAll('[id^="panel-"]:not(#panel-all)').forEach(panel => {
        const platform = panel.id.replace('panel-', '');
        const label = PLATFORM_LABELS[platform] || platform;

        const media = this.overrideMediaShown[platform]
          ? (this.platformMedia[platform] || [])
          : this.sharedMedia;
        const text = this.overrideTextShown[platform]
          ? (this.overrideText[platform] || '')
          : this.sharedText;

        const videos = media.filter(m => m.is_video);
        const images = media.filter(m => !m.is_video);

        if (!text.trim() && media.length === 0) {
          errors.push(`${label}: Post must have either text or media.`);
          return;
        }

        if (videos.length > 0 && images.length > 0) {
          errors.push(`${label}: Cannot mix images and videos in the same post.`);
          return;
        }

        if (videos.length > 1) {
          errors.push(`${label}: Only one video is allowed per post.`);
        }

        if (images.length > 4) {
          errors.push(`${label}: Maximum 4 images are allowed per post.`);
        }
      });

      return errors;
    },

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
      if (!form) return false;

      this.saving = true;
      try {
        this.syncSharedMediaFormset();
        this.syncPlatformMediaJson();

        const formData = new FormData(form);
        formData.set('action', action);
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
        const resp = await fetch(form.action, {
          method: 'POST',
          body: formData,
          headers: { 'X-CSRFToken': csrfToken },
        });
        if (!resp.ok) return false;
        const data = await resp.json();
        if (data.post_id) this.postId = data.post_id;

        if (closeOnSuccess) {
          up.layer.accept();
        }
        this.isDirty = false;
        return true;
      } finally {
        this.saving = false;
      }
    },

    // ── Drag-and-drop media reorder ───────────────────────────────────────

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
      if (type === 'shared') arr = [...this.sharedMedia];
      else if (type === 'seed') arr = [...this.seedMedia];
      else if (type === 'platform') arr = [...(this.platformMedia[platform] || [])];
      else return;
      const [moved] = arr.splice(sourceIdx, 1);
      arr.splice(targetIndex, 0, moved);
      if (type === 'shared') {
        this.sharedMedia = arr;
        this.$nextTick(() => this.syncSharedMediaFormset());
      } else if (type === 'seed') {
        this.seedMedia = arr;
      } else if (type === 'platform') {
        this.platformMedia = { ...this.platformMedia, [platform]: arr };
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

  // ── Post List ────────────────────────────────────────────────────────────

  Alpine.data('postList', () => ({

    init() {
      this._handler = (e) => {
        const postId = e.detail?.post_id;
        if (!postId) return;
        // When a modal is open, up.reload() defaults to looking for the target
        // in the current (modal) layer. The card lives on root, so it's not found
        // and the insertion is silently skipped (.post-list works because it has
        // up-hungry which bypasses layer isolation). asCurrent() makes root the
        // current layer so Unpoly finds the card element where it actually lives.
        up.layer.root.asCurrent(() => {
          const cardEl = document.getElementById(`post-card-${postId}`);
          if (cardEl) {
            up.reload(cardEl);
          } else {
            up.reload('.post-list');
          }
        });
      };
      document.addEventListener('post-changed', this._handler);
    },

    destroy() {
      document.removeEventListener('post-changed', this._handler);
    },

  }));

  // ── Publish Panel ────────────────────────────────────────────────────────

  Alpine.data('publishPanel', () => ({

    // ── State ───────────────────────────────────────────────────────────
    view: 'options',       // 'options' | 'publishing' | 'results'
    postStatus: '',
    scheduledAt: '',
    scheduleError: '',
    validationErrors: [],
    scheduling: false,
    unscheduling: false,
    publishing: false,

    postId: null,
    publishUrl: null,
    scheduleUrl: null,
    unscheduleUrl: null,
    saveScheduledAtUrl: null,
    panelUrl: null,
    _sseCleanup: null,
    _saveDebounceTimer: null,
    _lastSavedScheduledAt: '',
    _savingScheduledAt: false,

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
      this.publishUrl          = this.$el.dataset.publishUrl;
      this.scheduleUrl         = this.$el.dataset.scheduleUrl;
      this.unscheduleUrl       = this.$el.dataset.unscheduleUrl;
      this.saveScheduledAtUrl  = this.$el.dataset.saveScheduledAtUrl;
      this.panelUrl            = this.$el.dataset.panelUrl;
      this._lastSavedScheduledAt = this.scheduledAt;
      this._ownLayer           = up.layer.current;

      // Watch scheduledAt and debounce-save to database
      this.$watch('scheduledAt', (val) => {
        if (val === this._lastSavedScheduledAt) return;
        clearTimeout(this._saveDebounceTimer);
        this._saveDebounceTimer = setTimeout(() => this._autoSaveScheduledAt(val), 600);
      });

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

    // ── Pre-publish validation via parent composer ─────────────────────────
    async _validateViaComposer() {
      try {
        const parentEl = this._ownLayer?.parent?.element;
        if (!parentEl) return [];
        const composerEl = parentEl.querySelector('[x-data]');
        if (!composerEl) return [];
        const composer = Alpine.$data(composerEl);
        if (composer && typeof composer.validateForPublish === 'function') {
          return composer.validateForPublish();
        }
      } catch (e) {
        console.warn('publishPanel: could not validate via composer', e);
      }
      return [];
    },

    // ── Save parent post ───────────────────────────────────────────────────
    async _saveParentPost() {
      // The publish panel opens as a child layer over the post composer.
      // Walk up the layer stack to find the postComposer Alpine component and save.
      try {
        const parentEl = this._ownLayer?.parent?.element;
        if (!parentEl) return;
        const composerEl = parentEl.querySelector('[x-data]');
        if (!composerEl) return;
        const composer = Alpine.$data(composerEl);
        if (composer && typeof composer.savePost === 'function') {
          await composer.savePost(false, 'draft');
        }
      } catch (e) {
        console.warn('publishPanel: could not save parent post', e);
      }
    },

    // ── Schedule ─────────────────────────────────────────────────────────
    async schedulePost() {
      this.scheduleError = '';
      this.validationErrors = [];
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

      const validationErrs = await this._validateViaComposer();
      if (validationErrs.length > 0) {
        this.validationErrors = validationErrs;
        return;
      }

      this.scheduling = true;
      await this._saveParentPost();
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
          if (data.validation_errors && data.validation_errors.length) {
            this.validationErrors = data.validation_errors;
          } else {
            this.scheduleError = data.error || 'Failed to schedule.';
          }
          return;
        }
        this.postStatus = data.status;
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
      this.validationErrors = [];

      const validationErrs = await this._validateViaComposer();
      if (validationErrs.length > 0) {
        this.validationErrors = validationErrs;
        return;
      }

      this.publishing = true;
      this.view = 'publishing';
      await this._saveParentPost();
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
      try {
        const resp = await fetch(this.publishUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken },
        });
        const data = await resp.json();
        if (!resp.ok) {
          if (data.validation_errors && data.validation_errors.length) {
            this.validationErrors = data.validation_errors;
          }
          this.publishing = false;
          this.view = 'options';
        } else if (data.queued && this.postId) {
          this.postStatus = 'publishing';
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
        this._sseCleanup = null;
      };

      this._sseCleanup = cleanup;
      document.addEventListener('publish-done', handler);

      timer = setTimeout(() => {
        cleanup();
        this.publishing = false;
        this.view = 'options';
      }, 6 * 60 * 1000);
    },

    destroy() {
      if (this._sseCleanup) this._sseCleanup();
      clearTimeout(this._saveDebounceTimer);
    },

    // ── Auto-save scheduledAt ─────────────────────────────────────────────
    async _autoSaveScheduledAt(val) {
      if (!this.saveScheduledAtUrl || this._savingScheduledAt) return;
      this._savingScheduledAt = true;
      const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value
        || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
      try {
        const body = new URLSearchParams();
        if (val) {
          const dt = new Date(val);
          if (!isNaN(dt.getTime())) {
            body.set('scheduled_at', dt.toISOString());
          }
        }
        const resp = await fetch(this.saveScheduledAtUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken, 'Content-Type': 'application/x-www-form-urlencoded' },
          body,
        });
        if (resp.ok) {
          this._lastSavedScheduledAt = val;
        }
      } catch (e) {
        console.warn('publishPanel: could not auto-save scheduled_at', e);
      } finally {
        this._savingScheduledAt = false;
      }
    },

    _onPublishDone(data) {
      this.publishing = false;
      this.postStatus = data.status;
      // Reload the panel via Unpoly so the server-rendered version (with links) is shown.
      if (this.panelUrl) {
        up.navigate({ url: this.panelUrl, layer: this._ownLayer, history: false });
      } else {
        this.view = 'results';
      }
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
