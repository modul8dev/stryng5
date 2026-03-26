/* ── Social Media Post Composer ── */

document.addEventListener('alpine:init', () => {
  'use strict';

  // ── Image Picker (loaded as Unpoly modal fragment) ─────────────────────

  Alpine.data('imagePicker', () => ({
    groups: [],
    currentGroupId: null,
    selected: {},   // {imageId: true/false}
    target: '',

    init() {
      const groupsEl = document.getElementById('picker-groups-data');
      if (groupsEl) {
        this.groups = JSON.parse(groupsEl.textContent);
        if (this.groups.length) this.currentGroupId = this.groups[0].id;
      }

      const selectedEl = document.getElementById('picker-selected-ids');
      if (selectedEl) {
        const ids = JSON.parse(selectedEl.textContent);
        ids.forEach(id => { this.selected[id] = true; });
      }

      const targetEl = document.getElementById('picker-target');
      if (targetEl) this.target = targetEl.value;
    },

    currentImages() {
      if (!this.currentGroupId) return [];
      const group = this.groups.find(g => g.id === this.currentGroupId);
      return group ? group.images : [];
    },

    currentGroupTitle() {
      const group = this.groups.find(g => g.id === this.currentGroupId);
      return group ? group.title : '';
    },

    selectGroup(group) {
      const isNew = this.currentGroupId !== group.id;
      this.currentGroupId = group.id;
      // Auto-select first image when switching to a new group
      if (isNew && group.images.length > 0) {
        const firstId = group.images[0].id;
        if (!this.selected[firstId]) {
          this.selected = { ...this.selected, [firstId]: true };
        }
      }
    },

    isSelected(imageId) {
      return !!this.selected[imageId];
    },

    groupHasSelected(group) {
      return group.images.some(img => !!this.selected[img.id]);
    },

    toggle(imageId) {
      this.selected = { ...this.selected, [imageId]: !this.selected[imageId] };
    },

    confirm() {
      const urlMap = {};
      const groupMap = {};
      this.groups.forEach(g => g.images.forEach(img => {
        urlMap[img.id] = img.url;
        groupMap[img.id] = g.id;
      }));
      const imageIds = Object.entries(this.selected)
        .filter(([, v]) => v)
        .map(([id]) => parseInt(id, 10));
      up.layer.accept({ target: this.target, imageIds, urls: urlMap, groupMap });
    },

    cancel() {
      up.layer.dismiss();
    },
  }));

  // ── Post Composer ──────────────────────────────────────────────────────

  Alpine.data('postComposer', () => ({
    PLATFORM_LIMITS: {
      linkedin: 3000,
      x: 280,
      facebook: 63206,
      instagram: 2200,
    },

    activeTab: 'all',
    sharedText: '',
    overrideTextShown: {},
    overrideMediaShown: {},
    overrideText: {},
    textPrefilled: {},

    // ── Image state ───────────────────────────────────────────────────────
    sharedImages: [],        // [{mediaId, imageId, url}]
    deletedShared: [],       // [{mediaId, imageId}] — existing records removed
    platformImages: {},      // {platform: [{mediaId, imageId, url}]}

    // ── Lifecycle ─────────────────────────────────────────────────────────

    init() {
      const ta = this.$el.querySelector('#id_shared_text');
      if (ta) this.sharedText = ta.value;

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

    // ── Image Picker (Unpoly modal) ───────────────────────────────────────

    openPicker(target) {
      const currentImages = target === 'shared'
        ? this.sharedImages
        : (this.platformImages[target.replace('platform:', '')] || []);
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
