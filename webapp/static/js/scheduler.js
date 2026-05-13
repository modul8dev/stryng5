function schedulerApp() {
    return {
        calendar: null,
        platformFilter: '',
        statusFilter: '',

        init() {
            const calendarEl = document.getElementById('scheduler-calendar');
            if (!calendarEl) return;

            const eventsUrl = calendarEl.dataset.eventsUrl;
            const projectTimezone = calendarEl.dataset.timezone || 'local';
            const self = this;

            this.calendar = new FullCalendar.Calendar(calendarEl, {
                timeZone: projectTimezone,
                initialView: 'dayGridMonth',
                headerToolbar: {
                    left: 'prev,next today',
                    center: 'title',
                    right: 'dayGridMonth,timeGridWeek,timeGridDay',
                },
                buttonText: {
                    today: 'Today',
                    month: 'Month',
                    week: 'Week',
                    day: 'Day',
                },
                nowIndicator: true,
                editable: true,
                eventStartEditable: true,
                eventDurationEditable: false,
                dayMaxEvents: 3,
                moreLinkClick: 'day',
                height: 'auto',

                events: function(info, successCallback, failureCallback) {
                    const params = new URLSearchParams({
                        start: info.startStr,
                        end: info.endStr,
                    });
                    if (self.platformFilter) params.set('platform', self.platformFilter);
                    if (self.statusFilter) params.set('status', self.statusFilter);

                    fetch(eventsUrl + '?' + params.toString())
                        .then(r => r.json())
                        .then(data => successCallback(data))
                        .catch(err => failureCallback(err));
                },

                eventContent: function(arg) {
                    const props = arg.event.extendedProps;
                    const timeText = arg.timeText;
                    const title = arg.event.title;

                    const platformColors = {
                        linkedin: 'bg-blue-100 text-blue-700',
                        x: 'bg-zinc-200 text-zinc-700',
                        facebook: 'bg-blue-100 text-blue-800',
                        instagram: 'bg-pink-100 text-pink-700',
                    };

                    const platformLabels = {
                        linkedin: 'Li',
                        x: 'X',
                        facebook: 'Fb',
                        instagram: 'Ig',
                    };

                    function buildStatusBadge(status, processingStatus) {
                        if (processingStatus === 'generating') {
                            return '<span class="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-700 animate-pulse">'
                                + '<svg class="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">'
                                + '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>'
                                + '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>'
                                + '</svg>Generating</span>';
                        }
                        var badgeStyles = {
                            draft:      'bg-zinc-100 text-zinc-600',
                            scheduled:  'bg-amber-100 text-amber-700',
                            publishing: 'bg-amber-100 text-amber-700 animate-pulse',
                            published:  'bg-emerald-100 text-emerald-700',
                            failed:     'bg-red-100 text-red-700',
                        };
                        var badgeLabels = {
                            draft:      'Draft',
                            scheduled:  'Scheduled',
                            publishing: 'Publishing\u2026',
                            published:  'Published',
                            failed:     'Failed',
                        };
                        var bc = badgeStyles[status] || 'bg-zinc-100 text-zinc-600';
                        var bl = badgeLabels[status] || self.escapeHtml(status);
                        return '<span class="inline-flex items-center rounded-full ' + bc + ' px-2.5 py-0.5 text-xs font-medium">' + bl + '</span>';
                    }

                    let html = '<div class="scheduler-event-card">';

                    // Header: status badge + time
                    html += '<div class="scheduler-event-header">';
                    html += buildStatusBadge(props.status, props.processingStatus);
                    if (timeText) {
                        html += '<span class="scheduler-event-time">' + self.escapeHtml(timeText) + '</span>';
                    }
                    html += '</div>';

                    // Full-width media
                    if (props.thumbnail) {
                        html += '<div class="scheduler-event-thumb">';
                        if (props.isVideo) {
                            html += '<video src="' + self.escapeHtml(props.thumbnail) + '" muted preload="metadata" playsinline class="scheduler-event-video"></video>';
                        } else {
                            html += '<img src="' + self.escapeHtml(props.thumbnail) + '" alt="">';
                        }
                        html += '</div>';
                    }

                    // Body: caption
                    html += '<div class="scheduler-event-body">';

                    if (props.caption) {
                        html += '<div class="scheduler-event-caption">' + self.escapeHtml(props.caption) + '</div>';
                    }

                    if (props.platforms && props.platforms.length) {
                        html += '<div class="scheduler-event-platforms">';
                        props.platforms.forEach(function(p) {
                            var pc = platformColors[p] || '';
                            var pl = platformLabels[p] || p;
                            html += '<span class="scheduler-event-badge ' + pc + '">' + self.escapeHtml(pl) + '</span>';
                        });
                        html += '</div>';
                    }

                    html += '</div></div>';

                    return { html: html };
                },

                eventClick: function(info) {
                    info.jsEvent.preventDefault();
                    var editUrl = info.event.extendedProps.editUrl;
                    up.layer.open({
                        url: editUrl,
                        mode: 'modal',
                        size: 'large',
                        history: false,
                        dismissable: false,
                        onAccepted: function() {
                            self.calendar.refetchEvents();
                        },
                    });
                },

                eventDrop: function(info) {
                    var newStart = info.event.start;
                    var now = new Date();

                    if (newStart < now) {
                        info.revert();
                        self.showToast('Cannot schedule in the past', 'error');
                        return;
                    }

                    var csrfToken = self.getCookie('csrftoken');

                    fetch('/scheduler/api/reschedule/' + info.event.id + '/', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': csrfToken,
                        },
                        body: JSON.stringify({
                            scheduled_at: newStart.toISOString(),
                        }),
                    })
                    .then(function(r) { return r.json(); })
                    .then(function(data) {
                        if (data.error) {
                            info.revert();
                            self.showToast(data.error, 'error');
                        } else {
                            self.showToast('Post rescheduled', 'success');
                        }
                    })
                    .catch(function() {
                        info.revert();
                        self.showToast('Failed to reschedule', 'error');
                    });
                },

                eventDidMount: function(info) {
                    info.el.style.backgroundColor = 'transparent';
                    info.el.style.borderColor = 'transparent';
                },
            });

            this.calendar.render();

            // Listen for SSE post-changed events and surgically update the
            // matching calendar event without triggering a full refetch.
            this._postChangedHandler = function(e) {
                var detail = e.detail || {};
                var postId = detail.post_id;
                if (!postId) return;

                var fcEvent = self.calendar.getEventById(postId);
                if (!fcEvent) return; // event not in the current view range — ignore

                fetch('/scheduler/api/event/' + postId + '/')
                    .then(function(r) {
                        if (!r.ok) {
                            // Post may have been unscheduled; remove it from the calendar
                            if (r.status === 404) fcEvent.remove();
                            return null;
                        }
                        return r.json();
                    })
                    .then(function(data) {
                        if (!data) return;
                        // Update start time (handles reschedules)
                        fcEvent.setStart(data.start);
                        // Update all extendedProps so eventContent re-renders correctly
                        var ep = data.extendedProps || {};
                        Object.keys(ep).forEach(function(key) {
                            fcEvent.setExtendedProp(key, ep[key]);
                        });
                    })
                    .catch(function() {}); // best-effort; ignore transient errors
            };
            document.addEventListener('post-changed', this._postChangedHandler);

            // Listen for generation-done SSE events to instantly reflect
            // processingStatus changes without waiting for a full re-fetch.
            this._generationDoneHandler = function(e) {
                var detail = e.detail || {};
                var postId = detail.post_id;
                if (!postId) return;
                var fcEvent = self.calendar.getEventById(postId);
                if (!fcEvent) return;
                fcEvent.setExtendedProp('processingStatus', detail.processing_status || 'idle');
            };
            document.addEventListener('generation-done', this._generationDoneHandler);

            // Clean up on Unpoly layer dismissal / navigation
            document.addEventListener('up:location:changed', this._removePostChangedHandler.bind(this), { once: true });
        },

        _removePostChangedHandler() {
            if (this._postChangedHandler) {
                document.removeEventListener('post-changed', this._postChangedHandler);
                this._postChangedHandler = null;
            }
            if (this._generationDoneHandler) {
                document.removeEventListener('generation-done', this._generationDoneHandler);
                this._generationDoneHandler = null;
            }
        },

        refetch() {
            if (this.calendar) {
                this.calendar.refetchEvents();
            }
        },

        escapeHtml(str) {
            var div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        },

        getCookie(name) {
            var value = '; ' + document.cookie;
            var parts = value.split('; ' + name + '=');
            if (parts.length === 2) return parts.pop().split(';').shift();
            return '';
        },

        showToast(message, type) {
            var toast = document.createElement('div');
            toast.className = 'fixed bottom-4 right-4 z-50 rounded-xl border px-4 py-3 text-sm shadow-lg transition-all duration-300 '
                + (type === 'error'
                    ? 'border-red-200 bg-red-50 text-red-800'
                    : 'border-emerald-200 bg-emerald-50 text-emerald-800');
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(function() {
                toast.style.opacity = '0';
                setTimeout(function() { toast.remove(); }, 300);
            }, 3000);
        },
    };
}
