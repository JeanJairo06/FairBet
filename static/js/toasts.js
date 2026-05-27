document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-toast]').forEach((toast) => {
        const close = () => {
            toast.classList.add('app-toast--leaving');
            window.setTimeout(() => toast.remove(), 220);
        };

        const closeButton = toast.querySelector('[data-toast-close]');
        closeButton?.addEventListener('click', close);
        window.setTimeout(close, 5200);
    });
});
