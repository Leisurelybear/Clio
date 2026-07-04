const container = document.getElementById('toast-container');
const MAX_VISIBLE = 3;
let queue = [];

function addToast(message, type = 'info', duration = 4000) {
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icons = { success: '\u2713', error: '!', warning: '\u25CC', info: 'i' };

  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || 'i'}</span>
    <span class="toast-message">${message}</span>
    <button class="toast-close">&times;</button>
  `;

  toast.querySelector('.toast-close').onclick = () => removeToast(toast);

  const visible = container.children.length;
  if (visible >= MAX_VISIBLE) {
    queue.push(toast);
  } else {
    container.appendChild(toast);
    if (duration > 0) {
      setTimeout(() => removeToast(toast), duration);
    }
  }
}

function removeToast(toast) {
  if (toast.classList.contains('removing')) return;
  toast.classList.add('removing');
  toast.addEventListener('animationend', () => {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
    if (queue.length > 0) {
      const next = queue.shift();
      container.appendChild(next);
      setTimeout(() => removeToast(next), 4000);
    }
  }, { once: true });
}

export { addToast };
