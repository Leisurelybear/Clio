const STORAGE_KEY = 'vlog_ui_theme';

export function initTheme() {
  const saved = localStorage.getItem(STORAGE_KEY);
  const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;

  if (saved === 'light') {
    document.body.classList.add('light-theme');
    document.body.classList.remove('dark-theme');
  } else if (saved === 'dark') {
    document.body.classList.remove('light-theme');
    document.body.classList.add('dark-theme');
  } else if (prefersLight) {
    document.body.classList.add('light-theme');
    document.body.classList.remove('dark-theme');
  }
}

export function toggleTheme() {
  const isLight = document.body.classList.toggle('light-theme');
  document.body.classList.toggle('dark-theme', !isLight);
  localStorage.setItem(STORAGE_KEY, isLight ? 'light' : 'dark');
  return isLight;
}
