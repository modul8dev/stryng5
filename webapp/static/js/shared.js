// ── Global cleanup for Alpine fragments ──
up.on('up:fragment:destroyed', (event) => {
    // destroyTree handles the check internally
    Alpine.destroyTree(event.fragment); 
});