/* ── Compiled by Unpoly so it runs every time the fragment is inserted ── */

/* ── Add a URL image row to the formset (called from up-on-accepted) ── */
function mlAddUrlImageRow(url) {
  var container = document.querySelector('#formset-container');
  var emptyTemplate = document.querySelector('#empty-url-form');
  if (!container || !emptyTemplate) return;

  var form = container.closest('form');
  var totalInput = form.querySelector('[name$="-TOTAL_FORMS"]');
  var idx = parseInt(totalInput.value, 10);

  var clone = emptyTemplate.content.cloneNode(true);
  clone.querySelectorAll('[name], [id], [for]').forEach(function (el) {
    ['name', 'id', 'for'].forEach(function (attr) {
      var val = el.getAttribute(attr);
      if (val) el.setAttribute(attr, val.replace(/__prefix__/g, idx));
    });
  });

  var urlInput = clone.querySelector('[name$="-external_url"]');
  if (urlInput) urlInput.value = url;

  var img = clone.querySelector('.preview-img');
  var noPreview = clone.querySelector('.no-preview');
  if (img) { img.src = url; img.classList.remove('hidden'); }
  if (noPreview) noPreview.classList.add('hidden');

  container.appendChild(clone);
  totalInput.value = idx + 1;
}

/* ── Product Import Modal — Alpine.js component for the import overlay ──
 *
 * When importing=true, listens for media_library:import_completed (accepts
 * the layer) or media_library:import_error (shows inline error).
 *
 * Usage in template:
 *   <div x-data="productImportModal({ importing: true })">
 */
function productImportModal({ importing = false } = {}) {
  return {
    importing,
    error: '',

    init() {
      if (!this.importing) return;
      this._bindEvents();
    },

    _bindEvents() {
      this._onCompleted = () => {
        this._cleanup();
        try {
          if (up.layer.count > 1) up.layer.accept();
        } catch (e) {}
      };

      this._onError = (e) => {
        this._cleanup();
        this.importing = false;
        this.error = (e.detail && e.detail.error) || 'Import failed.';
      };

      document.addEventListener('media_library:import_completed', this._onCompleted);
      document.addEventListener('media_library:import_error', this._onError);
    },

    _cleanup() {
      document.removeEventListener('media_library:import_completed', this._onCompleted);
      document.removeEventListener('media_library:import_error', this._onError);
    },

    destroy() {
      this._cleanup();
    },
  };
}

up.compiler('#formset-container', function (container) {
  'use strict';

  var form = container.closest('form');
  var addBtn = form.querySelector('#add-image');
  var emptyTemplate = form.querySelector('#empty-form');

  function getTotalFormsInput() {
    return form.querySelector('[name$="-TOTAL_FORMS"]');
  }

  function getTotalForms() {
    return parseInt(getTotalFormsInput().value, 10);
  }

  function setTotalForms(val) {
    getTotalFormsInput().value = val;
  }

  /* ── Preview an image from a file input ── */
  function previewImage(input) {
    var row = input.closest('.image-row');
    if (!row) return;
    var img = row.querySelector('.preview-img');
    var noPreview = row.querySelector('.no-preview');
    if (!input.files || !input.files[0]) return;

    var reader = new FileReader();
    reader.onload = function (e) {
      img.src = e.target.result;
      img.classList.remove('hidden');
      if (noPreview) noPreview.classList.add('hidden');
    };
    reader.readAsDataURL(input.files[0]);
  }

  /* ── Add a new image row ── */
  if (addBtn && emptyTemplate) {
    addBtn.addEventListener('click', function () {
      var idx = getTotalForms();
      var clone = emptyTemplate.content.cloneNode(true);

      clone.querySelectorAll('[name], [id], [for]').forEach(function (el) {
        ['name', 'id', 'for'].forEach(function (attr) {
          var val = el.getAttribute(attr);
          if (val) {
            el.setAttribute(attr, val.replace(/__prefix__/g, idx));
          }
        });
      });

      container.appendChild(clone);
      setTotalForms(idx + 1);

      var newRow = container.lastElementChild;
      var fileInput = newRow.querySelector('input[type="file"]');
      if (fileInput) {
        var cancelHandler = function () {
          setTimeout(function () {
            if (!fileInput.files || fileInput.files.length === 0) {
              newRow.remove();
              setTotalForms(getTotalForms() - 1);
            }
          }, 300);
        };
        fileInput.addEventListener('change', function () {
          window.removeEventListener('focus', cancelHandler);
          previewImage(fileInput);
        }, { once: true });
        window.addEventListener('focus', cancelHandler, { once: true });
        fileInput.click();
      }
    });
  }

  /* ── Event delegation on the container ── */
  container.addEventListener('change', function (e) {
    if (e.target.type === 'file') {
      previewImage(e.target);
    }
  });

  container.addEventListener('click', function (e) {
    var removeBtn = e.target.closest('.remove-row');
    if (removeBtn) {
      var row = removeBtn.closest('.image-row');
      if (row) row.remove();
    }
  });

  /* ── Style delete-toggle for existing images ── */
  container.addEventListener('change', function (e) {
    var checkbox = e.target;
    if (checkbox.type !== 'checkbox') return;
    var label = checkbox.closest('.delete-toggle');
    if (!label) return;
    var row = checkbox.closest('.image-row');
    if (!row) return;

    if (checkbox.checked) {
      row.classList.add('opacity-40');
      label.classList.remove('btn-outline');
      label.querySelector('.delete-label').textContent = '↺';
    } else {
      row.classList.remove('opacity-40');
      label.classList.add('btn-outline');
      label.querySelector('.delete-label').textContent = '✕';
    }
  });

  /* ── Hide the raw checkbox inside delete-toggle labels ── */
  container.querySelectorAll('.delete-toggle input[type="checkbox"]').forEach(function (cb) {
    cb.style.position = 'absolute';
    cb.style.opacity = '0';
    cb.style.width = '0';
    cb.style.height = '0';
  });

  /* ── Paste image from clipboard ── */
  function addPastedImageRow(file) {
    if (!emptyTemplate) return;
    var idx = getTotalForms();
    var clone = emptyTemplate.content.cloneNode(true);

    clone.querySelectorAll('[name], [id], [for]').forEach(function (el) {
      ['name', 'id', 'for'].forEach(function (attr) {
        var val = el.getAttribute(attr);
        if (val) el.setAttribute(attr, val.replace(/__prefix__/g, idx));
      });
    });

    container.appendChild(clone);
    setTotalForms(idx + 1);

    var newRow = container.lastElementChild;
    var fileInput = newRow.querySelector('input[type="file"]');
    if (fileInput) {
      var dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      previewImage(fileInput);
    }
  }

  function handlePaste(e) {
    if (!container.isConnected) {
      document.removeEventListener('paste', handlePaste);
      return;
    }
    var items = e.clipboardData && e.clipboardData.items;
    if (!items) return;
    for (var i = 0; i < items.length; i++) {
      if (items[i].type.indexOf('image') !== -1) {
        var file = items[i].getAsFile();
        if (file) addPastedImageRow(file);
      }
    }
  }

  document.addEventListener('paste', handlePaste);

});

/* ── Social Media Post Composer ── */

document.addEventListener('alpine:init', () => {
  'use strict';

  // ── Image Picker (loaded as Unpoly modal fragment) ─────────────────────

  Alpine.data('imagePicker', () => ({
    groups: [],
    currentGroupId: null,
    selected: {},        // {imageId: true/false}
    selectedOrder: [],   // insertion-order list of selected IDs (for FIFO)
    target: '',
    maxImages: 0,
    search: '',
    typeFilter: 'all',
    showSelectedOnly: false,
    _refreshUrl: '',
    _createUrl: '',
    _editUrlBase: '',

    init() {
      const groupsEl = document.getElementById('picker-groups-data');
      if (groupsEl) {
        this.groups = JSON.parse(groupsEl.textContent);
        // No group is focused by default
      }

      const selectedEl = document.getElementById('picker-selected-ids');
      if (selectedEl) {
        const ids = JSON.parse(selectedEl.textContent);
        ids.forEach(id => {
          this.selected[id] = true;
          this.selectedOrder.push(id);
        });
      }

      const targetEl = document.getElementById('picker-target');
      if (targetEl) this.target = targetEl.value;

      const maxEl = document.getElementById('picker-max-images');
      if (maxEl && maxEl.value) this.maxImages = parseInt(maxEl.value, 10) || 0;

      // Read URL config from data attributes on the root element
      const root = document.getElementById('image-picker');
      if (root) {
        this._refreshUrl = root.dataset.refreshUrl || '';
        this._createUrl = root.dataset.createUrl || '';
        this._editUrlBase = root.dataset.editUrlBase || '';
      }
    },

    filteredGroups() {
      const q = this.search.trim().toLowerCase();
      return this.groups.filter(g => {
        if (this.typeFilter !== 'all' && g.type !== this.typeFilter) return false;
        if (!q) return true;
        return g.title.toLowerCase().includes(q) || (g.description || '').toLowerCase().includes(q);
      });
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
      // Auto-select first image when switching to a new group (uses FIFO if at limit)
      if (isNew && group.images.length > 0) {
        const firstId = group.images[0].id;
        if (!this.selected[firstId]) {
          this._addToSelection(firstId);
        }
      }
    },

    isSelected(imageId) {
      return !!this.selected[imageId];
    },

    groupHasSelected(group) {
      return group.images.some(img => !!this.selected[img.id]);
    },

    selectedCount() {
      return this.selectedOrder.length;
    },

    atMax() {
      return this.maxImages > 0 && this.selectedOrder.length >= this.maxImages;
    },

    _addToSelection(imageId) {
      const newSelected = { ...this.selected };
      const newOrder = [...this.selectedOrder];
      if (this.maxImages > 0 && newOrder.length >= this.maxImages) {
        // FIFO: evict the oldest selection
        const oldest = newOrder.shift();
        if (oldest !== undefined) newSelected[oldest] = false;
      }
      newSelected[imageId] = true;
      newOrder.push(imageId);
      this.selected = newSelected;
      this.selectedOrder = newOrder;
    },

    toggle(imageId) {
      if (this.selected[imageId]) {
        // Deselect
        this.selected = { ...this.selected, [imageId]: false };
        this.selectedOrder = this.selectedOrder.filter(id => id !== imageId);
      } else {
        this._addToSelection(imageId);
      }
    },

    allSelectedImages() {
      const idToImg = {};
      this.groups.forEach(g => g.images.forEach(img => {
        idToImg[img.id] = img;
      }));
      return this.selectedOrder.map(id => idToImg[id]).filter(Boolean);
    },

    sidebarImages() {
      return this.showSelectedOnly ? this.allSelectedImages() : this.currentImages();
    },

    editGroup(groupId) {
      const url = this._editUrlBase.replace('/0/', '/' + groupId + '/');
      up.layer.open({ url, onAccepted: () => this.refreshGroups() });
    },

    createGroup() {
      up.layer.open({ url: this._createUrl, onAccepted: () => this.refreshGroups() });
    },

    refreshGroups() {
      const url = this._refreshUrl + '?format=json';
      fetch(url)
        .then(r => r.json())
        .then(data => { this.groups = data.groups; });
    },

    confirm() {
      const urlMap = {};
      const groupMap = {};
      this.groups.forEach(g => g.images.forEach(img => {
        urlMap[img.id] = img.url;
        groupMap[img.id] = g.id;
      }));
      const imageIds = this.selectedOrder.map(id => parseInt(id, 10));
      up.layer.accept({ target: this.target, imageIds, urls: urlMap, groupMap });
    },

    cancel() {
      up.layer.dismiss();
    },
  }));

  // ── Catalog (products + media library combined view) ─────────────────

  Alpine.data('catalog', () => ({
    search: '',
    activeType: 'all',

    visible(el) {
      const typeMatch = this.activeType === 'all' || el.dataset.type === this.activeType;
      if (!typeMatch) return false;
      if (!this.search) return true;
      const q = this.search.toLowerCase();
      return (el.dataset.title || '').includes(q) || (el.dataset.desc || '').includes(q);
    },
  }));
});
