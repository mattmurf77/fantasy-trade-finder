// Local illustrative views. Keep focus and scroll position on the selected step.
(() => {
  const content = document.getElementById('landing-step-content');
  if (!content) return;
  const buttons = document.querySelectorAll('[data-landing-step]');
  buttons.forEach(button => button.addEventListener('click', () => {
    const template = document.getElementById(`landing-step-template-${button.dataset.landingStep}`);
    if (!template) return;
    content.replaceChildren(template.content.cloneNode(true));
    buttons.forEach(item => item.setAttribute('aria-pressed', String(item === button)));
  }));
})();
