// Bulk selection is local to each transfer direction. Only the individual
// Pokémon checkboxes are submitted to the existing finalize endpoint.
(() => {
  const form = document.getElementById('transfer-form');
  if (!form) return;

  form.querySelectorAll('[data-selection-group]').forEach((toolbar) => {
    const master = toolbar.querySelector('[data-select-all]');
    const count = toolbar.querySelector('.selection-count');
    const items = Array.from(form.querySelectorAll(
      `input[type="checkbox"][name="${toolbar.dataset.selectionGroup}"]`
    ));

    const sync = () => {
      const enabled = items.filter((item) => !item.disabled);
      const selected = enabled.filter((item) => item.checked).length;
      master.disabled = enabled.length === 0;
      master.checked = enabled.length > 0 && selected === enabled.length;
      master.indeterminate = selected > 0 && selected < enabled.length;
      count.textContent = `${selected} of ${enabled.length} selected`;
    };

    master.addEventListener('change', () => {
      items.filter((item) => !item.disabled).forEach((item) => {
        item.checked = master.checked;
      });
      sync();
    });
    items.forEach((item) => item.addEventListener('change', sync));
    form.addEventListener('reset', () => queueMicrotask(sync));
    window.addEventListener('pageshow', sync);
    sync();
    toolbar.hidden = false;
  });
})();
