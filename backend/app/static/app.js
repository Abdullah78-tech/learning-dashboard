'use strict';
const toggle = document.querySelector('[data-password-toggle]');
toggle?.addEventListener('click', () => {
  const input = document.getElementById('password');
  const visible = input.type === 'password';
  input.type = visible ? 'text' : 'password';
  toggle.textContent = visible ? 'Hide' : 'Show';
  toggle.setAttribute('aria-label', visible ? 'Hide password' : 'Show password');
});
const sidebar = document.getElementById('sidebar');
const menu = document.querySelector('.menu-toggle');
menu?.addEventListener('click', () => {
  const open = sidebar.classList.toggle('is-open');
  menu.setAttribute('aria-expanded', String(open));
});
const titles = { overview: 'Overview', projects: 'Projects', analytics: 'Analytics', integrations: 'Integrations', profile: 'My profile' };
document.querySelectorAll('[data-panel]').forEach(button => button.addEventListener('click', () => {
  const id = button.dataset.panel;
  document.querySelectorAll('.dashboard-panel').forEach(panel => { panel.hidden = panel.id !== `panel-${id}`; });
  document.querySelectorAll('.nav-item[data-panel]').forEach(item => {
    const selected = item.dataset.panel === id;
    item.classList.toggle('active', selected);
    if (selected) item.setAttribute('aria-current', 'page'); else item.removeAttribute('aria-current');
  });
  document.getElementById('breadcrumb-title').textContent = titles[id];
  sidebar?.classList.remove('is-open');
  menu?.setAttribute('aria-expanded', 'false');
  const heading = document.querySelector(`#panel-${id} h1`);
  heading?.setAttribute('tabindex', '-1');
  heading?.focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}));
let toastTimeout;
document.querySelectorAll('[data-demo]').forEach(button => button.addEventListener('click', () => {
  const toast = document.getElementById('toast');
  toast.textContent = button.dataset.demo;
  toast.hidden = false;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { toast.hidden = true; }, 5500);
}));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    sidebar?.classList.remove('is-open');
    menu?.setAttribute('aria-expanded', 'false');
    const toast = document.getElementById('toast');
    if (toast) toast.hidden = true;
  }
});
