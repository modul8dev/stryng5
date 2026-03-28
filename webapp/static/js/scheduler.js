function schedulerApp() {
    return {
        calendar: null,
        platformFilter: '',
        statusFilter: '',

        init() {
            const calendarEl = document.getElementById('scheduler-calendar');
            if (!calendarEl) return;

            const eventsUrl = calendarEl.dataset.eventsUrl;
            const self = this;

            this.calendar = new FullCalendar.Calendar(calendarEl, {
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

                    const statusColors = {
                        draft: 'bg-zinc-200 text-zinc-600',
                        scheduled: 'bg-amber-400 text-white',
                        published: 'bg-blue-500 text-white',
                        failed: 'bg-red-500 text-white',
                    };

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

                    var sc = statusColors[props.status] || 'bg-zinc-200 text-zinc-600';

                    let html = '<div class="scheduler-event-card">';

                    // Header: status badge + time
                    html += '<div class="scheduler-event-header">';
                    html += '<span class="scheduler-event-status ' + sc + '">' + self.escapeHtml(props.status) + '</span>';
                    if (timeText) {
                        html += '<span class="scheduler-event-time">' + self.escapeHtml(timeText) + '</span>';
                    }
                    html += '</div>';

                    // Full-width image
                    if (props.thumbnail) {
                        html += '<div class="scheduler-event-thumb">'
                            + '<img src="' + self.escapeHtml(props.thumbnail) + '" alt="">'
                            + '</div>';
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
