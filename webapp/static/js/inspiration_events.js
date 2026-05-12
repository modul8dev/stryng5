document.addEventListener('inspiration:card_ready', function (e) {
  var slotId = e.detail && e.detail.slot_id;
  var cacheKey = e.detail && e.detail.cache_key;
  if (!slotId || !cacheKey) return;

  var slot = document.getElementById('inspiration-slot-' + slotId);
  if (!slot) return;

  var url = slot.dataset.cardUrl;
  if (!url) return;

  fetch(url, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    credentials: 'same-origin'
  })
    .then(function (resp) { return resp.text(); })
    .then(function (html) {
      if (!html.trim()) return;
      var temp = document.createElement('div');
      temp.innerHTML = html;
      var newCard = temp.firstElementChild;
      if (newCard) {
        slot.replaceWith(newCard);
      }
    })
    .catch(function (err) {
      console.debug('[Inspiration] failed to load card for slot', slotId, err);
    });
});
