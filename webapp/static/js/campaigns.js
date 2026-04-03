/**
 * Campaign Chat — Alpine.js controller
 *
 * Handles SSE streaming, message rendering, and conversation management.
 */
function campaignChat() {
    return {
        pendingUserMessage: '',
        inputText: '',
        isStreaming: false,
        streamedText: '',
        steps: [],
        currentAgent: 'Coordinator',
        _stepId: 0,

        init() {
            // Configure marked renderer to make images compact in chat bubbles
            if (window.marked) {
                const renderer = new marked.Renderer();
                const originalImage = renderer.image.bind(renderer);
                renderer.image = function(token) {
                    // originalImage returns an <img> string; we wrap it for sizing
                    const base = originalImage(token);
                    // inject inline style for small thumbnails
                    return base.replace('<img ', '<preview-img style="max-height:120px;max-width:200px;border-radius:6px;display:inline-block;margin:2px;" ');
                };
                marked.use({ renderer });

                document.querySelectorAll('.js-markdown').forEach(el => {
                    el.innerHTML = marked.parse(el.dataset.content || '');
                });
            }
            this.$nextTick(() => this.scrollToBottom());
        },

        getCSRFToken() {
            const el = document.querySelector('[name=csrfmiddlewaretoken]');
            if (el) return el.value;
            const match = document.cookie.match(/csrftoken=([^;]+)/);
            return match ? match[1] : '';
        },

        async sendMessage() {
            const text = this.inputText.trim();
            if (!text || this.isStreaming) return;

            const conversationId = this.getConversationId();
            if (!conversationId) return;

            this.pendingUserMessage = text;
            this.inputText = '';
            this.isStreaming = true;
            this.streamedText = '';
            this.steps = [];
            this.currentAgent = 'Coordinator';

            // Reset textarea height
            if (this.$refs.messageInput) {
                this.$refs.messageInput.style.height = 'auto';
            }
            this.scrollToBottom();

            try {
                const response = await fetch(`/campaigns/conversations/${conversationId}/send/`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this.getCSRFToken(),
                    },
                    body: JSON.stringify({ message: text }),
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop(); // keep incomplete line in buffer

                    let eventType = '';
                    let eventData = '';

                    for (const line of lines) {
                        if (line.startsWith('event: ')) {
                            eventType = line.slice(7).trim();
                        } else if (line.startsWith('data: ')) {
                            eventData = line.slice(6);
                        } else if (line === '' && eventType && eventData) {
                            this.handleSSEvent(eventType, eventData);
                            eventType = '';
                            eventData = '';
                            // Yield to the browser so Alpine can update the DOM between events
                            await new Promise(resolve => setTimeout(resolve, 0));
                        }
                    }
                }
            } catch (err) {
                console.error('Stream error:', err);
                this.streamedText += '\n\n*An error occurred. Please try again.*';
            } finally {
                this.finishStreaming();
            }
        },

        handleSSEvent(type, dataStr) {
            let data;
            try {
                data = JSON.parse(dataStr);
            } catch {
                return;
            }

            switch (type) {
                case 'text_delta':
                    this.streamedText += data.delta || '';
                    this.scrollToBottom();
                    break;

                case 'agent_update':
                    this.currentAgent = data.agent || 'Agent';
                    this._stepId++;
                    this.steps.push({
                        id: this._stepId,
                        label: `${data.agent} is working...`,
                    });
                    this.scrollToBottom();
                    break;

                case 'tool_call':
                    this._stepId++;
                    this.steps.push({
                        id: this._stepId,
                        label: `${data.agent}: calling ${this.formatToolName(data.tool)}`,
                    });
                    this.scrollToBottom();
                    break;

                case 'tool_output':
                    // Update the last step to show completion
                    if (this.steps.length > 0) {
                        const last = this.steps[this.steps.length - 1];
                        last.label = `${data.agent}: ${this.formatToolName(data.tool)} done`;
                    }
                    break;

                case 'handoff':
                    this._stepId++;
                    this.steps.push({
                        id: this._stepId,
                        label: `Handing off to ${data.to_agent}...`,
                    });
                    this.scrollToBottom();
                    break;

                case 'done':
                    // Stream complete
                    break;

                case 'error':
                    this.streamedText += `\n\n*Error: ${data.error || 'Unknown error'}*`;
                    this.scrollToBottom();
                    break;
            }
        },

        finishStreaming() {
            const pendingUser = this.pendingUserMessage;
            const assistantText = this.streamedText.trim();

            // Clear reactive state first so Alpine hides the streaming area
            this.isStreaming = false;
            this.pendingUserMessage = '';
            this.streamedText = '';
            this.steps = [];

            // Then commit both messages to the persistent DOM anchor
            if (pendingUser) {
                this.appendUserMessage(pendingUser);
            }
            if (assistantText) {
                this.appendAssistantMessage(assistantText);
            }
            this.scrollToBottom();
        },

        appendUserMessage(text) {
            const container = document.getElementById('dynamic-messages');
            if (!container) return;
            const div = document.createElement('div');
            div.className = 'flex justify-end';
            div.innerHTML = `
                <div class="max-w-2xl rounded-2xl rounded-br-md bg-indigo-600 px-4 py-3 text-sm text-white shadow-sm">
                    ${this.escapeHtml(text).replace(/\n/g, '<br>')}
                </div>`;
            container.appendChild(div);
        },

        appendAssistantMessage(text) {
            const container = document.getElementById('dynamic-messages');
            if (!container) return;
            const div = document.createElement('div');
            div.className = 'flex justify-start';
            div.innerHTML = `
                <div class="flex gap-3 w-full">
                    <div class="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-purple-600">
                        <svg xmlns="http://www.w3.org/2000/svg" class="size-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/>
                        </svg>
                    </div>
                    <div class="rounded-2xl rounded-tl-md bg-white px-4 py-3 text-sm text-zinc-800 shadow-sm border border-zinc-100 prose prose-sm max-w-none w-full">
                        ${this.formatMessage(text)}
                    </div>
                </div>`;
            container.appendChild(div);
        },

        formatMessage(text) {
            if (window.marked) {
                return marked.parse(text.trim());
            }
            // Fallback basic formatting
            let html = this.escapeHtml(text);
            html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
            html = html.replace(/\n/g, '<br>');
            return html;
        },

        formatToolName(name) {
            if (!name) return 'tool';
            return name.replace(/_/g, ' ');
        },

        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        getConversationId() {
            // Extract from URL: /campaigns/<id>/
            const match = window.location.pathname.match(/\/campaigns\/(\d+)\//);
            return match ? match[1] : null;
        },

        scrollToBottom() {
            this.$nextTick(() => {
                const thread = this.$refs.messageThread;
                if (thread) {
                    thread.scrollTop = thread.scrollHeight;
                }
            });
        },
    };
}
