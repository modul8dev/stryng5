up.compiler('[data-auto-provision]', function(el) {
    var pid = el.dataset.autoProvision;
    el.remove();
    up.layer.open({
        url: '/projects/provision/?project_id=' + pid,
        mode: 'modal',
        size: 'medium',
        history: false
    });
});
