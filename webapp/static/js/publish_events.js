/* ── Publish Events — SSE client for post publish status ── */

window.PostPublishEvents = (() => {
  'use strict';

  let source = null;
  let timeoutHandle = null;

  const TIMEOUT_MS = 6 * 60 * 1000; // 6 minutes — matches Q_CLUSTER timeout + grace

  function _cleanup() {
    if (source) { source.close(); source = null; }
    if (timeoutHandle) { clearTimeout(timeoutHandle); timeoutHandle = null; }
  }

  return {
    /**
     * Subscribe to publish-done events for the given post ID.
     * onDone({ status, successes, failures }) called once on completion.
     * onTimeout() called if no event arrives within TIMEOUT_MS.
     */
    subscribe(postId, onDone, onTimeout) {
      _cleanup();

      // ReconnectingEventSource (bundled with django-eventstream) handles
      // reconnects and Last-Event-ID tracking automatically.
      source = new ReconnectingEventSource(`/events/?channel=post-${postId}`);

      source.addEventListener('publish-done', (e) => {
        const data = JSON.parse(e.data);
        _cleanup();
        onDone(data);
      });

      source.addEventListener('stream-error', (e) => {
        const { condition } = JSON.parse(e.data);
        console.error('PostPublishEvents: stream-error', condition);
        _cleanup();
        if (onTimeout) onTimeout();
      });

      timeoutHandle = setTimeout(() => {
        _cleanup();
        if (onTimeout) onTimeout();
      }, TIMEOUT_MS);
    },

    unsubscribe: _cleanup,
  };
})();
