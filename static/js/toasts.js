// Auto-cerrar toasts del servidor (Django messages)
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-toast]').forEach(iniciarToast);
});

function iniciarToast(toast) {
    const close = () => {
        toast.classList.add('app-toast--leaving');
        window.setTimeout(() => toast.remove(), 220);
    };
    toast.querySelector('[data-toast-close]')?.addEventListener('click', close);
    window.setTimeout(close, 5200);
}

/**
 * Crea y muestra un toast programáticamente.
 * @param {string} mensaje  Texto del toast.
 * @param {'success'|'error'|'warning'|'info'} tipo
 */
function mostrarToast(mensaje, tipo = 'info') {
    const contenedor = obtenerContenedorToasts();
    const toast = document.createElement('div');
    toast.className = `app-toast app-toast--${tipo}`;
    toast.setAttribute('data-toast', '');
    toast.innerHTML = `
        <span>${mensaje}</span>
        <button class="app-toast__close" data-toast-close aria-label="Cerrar">&times;</button>
    `;
    contenedor.appendChild(toast);
    iniciarToast(toast);
}

function obtenerContenedorToasts() {
    let contenedor = document.getElementById('toast-container');
    if (!contenedor) {
        contenedor = document.createElement('div');
        contenedor.id = 'toast-container';
        contenedor.className = 'toast-stack';
        document.body.appendChild(contenedor);
    }
    return contenedor;
}
