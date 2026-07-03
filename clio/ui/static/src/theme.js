const STORAGE_KEY = 'vlog_ui_theme';

export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY);
  const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;

  if (saved === 'light') {
    document.body.classList.add('light-theme');
  } else if (saved === 'dark') {
    document.body.classList.remove('light-theme');
  } else if (prefersLight) {
    document.body.classList.add('light-theme');
  }
}

export function toggleTheme() {
  document.body.classList.toggle('light-theme');
  const isLight = document.body.classList.contains('light-theme');
  localStorage.setItem(STORAGE_KEY, isLight ? 'light' : 'dark');
  return isLight;
}
