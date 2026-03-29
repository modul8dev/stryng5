/* ── AI Textarea Component ── */

document.addEventListener('alpine:init', () => {
    'use strict';

    const ACTION_LABELS = {
        rewrite: 'Rewrite',
        improve: 'Improve',
        shorten: 'Shorten',
        expand: 'Expand',
        make_engaging: 'Make engaging',
        adapt_to_platform: 'Adapt to platform',
        add_cta: 'Add CTA',
        fix_grammar: 'Fix grammar',
    };

    const DEFAULT_ACTIONS = Object.keys(ACTION_LABELS);

    Alpine.data('aiTextarea', (cfg) => ({

        // ── Config ─────────────────────────────────────────────────────────
        endpoint: cfg.endpoint || '',
        actionsStr: cfg.actionsStr || '',
        showCustomInstruction: cfg.showCustomInstruction ?? false,
        customPlaceholder: cfg.customPlaceholder || 'Tell AI what to do with the text\u2026',
        showCharCount: cfg.showCharCount ?? false,
        autoHide: cfg.autoHide || 'never',
        hideDelay: cfg.hideDelay ?? 150,
        resultMode: cfg.resultMode || 'replace',
        platform: cfg.platform || '',
        language: cfg.language || '',

        // ── State ──────────────────────────────────────────────────────────
        fieldEl: null,
        instruction: '',
        processing: false,
        error: null,
        showTools: (cfg.autoHide || 'never') === 'never',
        hideTimer: null,
        actionsList: [],

        // ── Lifecycle ──────────────────────────────────────────────────────
        init() {
            this.fieldEl = this.$el.querySelector('textarea, input[type="text"]');
            if (!this.fieldEl) {
                console.warn('[aiTextarea] No textarea or text input found inside component.');
            }

            if (this.actionsStr.trim()) {
                this.actionsList = this.actionsStr
                    .split(',')
                    .map(a => a.trim())
                    .filter(Boolean);
            } else {
                this.actionsList = [...DEFAULT_ACTIONS];
            }

            this.$watch('processing', (val) => {
                if (this.fieldEl) {
                    this.fieldEl.classList.toggle('ai-field-processing', val);
                }
            });
        },

        // ── Field access ───────────────────────────────────────────────────
        getValue() {
            return this.fieldEl ? this.fieldEl.value : '';
        },

        setValue(value) {
            if (!this.fieldEl) return;
            this.fieldEl.value = value;
            this.fieldEl.dispatchEvent(new Event('input', { bubbles: true }));
            this.fieldEl.dispatchEvent(new Event('change', { bubbles: true }));
        },

        // ── Display helpers ────────────────────────────────────────────────
        charCountLabel() {
            const len = this.getValue().length;
            return `${len} character${len === 1 ? '' : 's'}`;
        },

        actionLabel(action) {
            return ACTION_LABELS[action] || action;
        },

        // ── Actions ────────────────────────────────────────────────────────
        runAction(action) {
            this.sendRequest({ action });
        },

        runCustomInstruction() {
            if (!this.instruction.trim()) return;
            this.sendRequest({ action: 'freeform', instruction: this.instruction });
        },

        async sendRequest({ action, instruction = '' }) {
            if (this.processing) return;

            const text = this.getValue();
            if (!text.trim() && !instruction.trim()) return;

            this.processing = true;
            this.error = null;
            this.$dispatch('ai-start', { action, instruction });

            try {
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
                const response = await fetch(this.endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': csrfToken,
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body: JSON.stringify({
                        text,
                        action: action || 'freeform',
                        instruction: instruction || '',
                        result_mode: this.resultMode,
                        platform: this.platform || undefined,
                        language: this.language || undefined,
                        field_name: this.fieldEl?.name || '',
                    }),
                });

                const data = await response.json();
                if (!response.ok || data.error) {
                    throw new Error(data.error || `Request failed (${response.status})`);
                }

                if (data.text !== undefined) {
                    let newValue;
                    if (this.resultMode === 'append') {
                        newValue = text + (text ? '\n\n' : '') + data.text;
                    } else if (this.resultMode === 'prepend') {
                        newValue = data.text + (text ? '\n\n' : '') + text;
                    } else {
                        newValue = data.text;
                    }
                    this.setValue(newValue);
                    this.instruction = '';
                    this.$dispatch('ai-success', { action, instruction, result: data.text });
                    this.$dispatch('ai-updated', { value: newValue });
                }
            } catch (err) {
                this.error = err.message || 'Something went wrong. Please try again.';
                this.$dispatch('ai-error', { action, instruction, message: this.error });
            } finally {
                this.processing = false;
            }
        },

        // ── Focus-based auto-hide ──────────────────────────────────────────
        handleFocusIn(event) {
            clearTimeout(this.hideTimer);
            if (this.autoHide === 'never') return;
            if (this.autoHide === 'textarea-blur') {
                if (event.target === this.fieldEl) {
                    this.showTools = true;
                }
            } else {
                // 'blur': show on any focus within
                this.showTools = true;
            }
        },

        handleFocusOut(event) {
            if (this.autoHide === 'never') return;
            const relatedTarget = event.relatedTarget;
            if (!relatedTarget || !this.$el.contains(relatedTarget)) {
                this.hideTimer = setTimeout(() => {
                    this.showTools = false;
                }, this.hideDelay);
            }
        },

    }));
});
