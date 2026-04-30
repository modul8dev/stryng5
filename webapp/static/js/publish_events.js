if (window.__USER_ID__) {
  const channel = 'user-' + window.__USER_ID__;
  window.SSE = new ReconnectingEventSource('/events/?channel=' + channel);

  window.SSE.onopen = function () { console.debug('[SSE] connected ' + channel); };
  window.SSE.onerror = function (e) { console.debug('[SSE] error ' + channel, e); };

  // All server-sent events use the default 'message' type with a 'type'
  // field in the JSON payload. A single listener here bridges them all to
  // document CustomEvents — no list to maintain, every event is handled.
  window.SSE.addEventListener('message', function (e) {
    var detail = JSON.parse(e.data || '{}');
    if (!detail.type) return;
    console.debug('[SSE] received', detail.type, detail);
    document.dispatchEvent(new CustomEvent(detail.type, { detail: detail }));
  });
}