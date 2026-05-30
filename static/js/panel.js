document.addEventListener('DOMContentLoaded', function() {
    // 1. Selector de Días Temporales para Autoexclusión
    const selectTipo = document.getElementById('id_tipo_autoexclusion');
    const contenedorDuracion = document.getElementById('contenedor-duracion');

    function evaluarVisibilidad() {
        if (selectTipo) {
            // Convertimos el valor a MAYÚSCULAS para que 'Temporal' o 'TEMPORAL' sean lo mismo
            const valorMayuscula = selectTipo.value.toUpperCase();
            
            if (valorMayuscula === 'TEMPORAL') {
                contenedorDuracion.style.display = 'block'; // Muestra las opciones de días
            } else {
                contenedorDuracion.style.display = 'none';  // Oculta si es Permanente
            }
        }
    }
    if (selectTipo) {
        // ESCUCHA cuando el usuario cambie de opción manualmente
        selectTipo.addEventListener('change', evaluarVisibilidad);
        
        // 🟢 TRUCO: Ejecuta la función AHORA MISMO para evaluar el estado inicial al cargar la página
        evaluarVisibilidad();
    }

    // 2. Ventana Modal de Confirmación Profesional
    const btnAutoexcluir = document.getElementById('btn-autoexcluir');
    const modal = document.getElementById('custom-confirm-modal');
    const modalCancel = document.getElementById('modal-cancel-btn');
    const modalConfirm = document.getElementById('modal-confirm-btn');
    const formularioAutoexclusion = btnAutoexcluir ? btnAutoexcluir.closest('form') : null;

    if (btnAutoexcluir && modal) {
        btnAutoexcluir.addEventListener('click', function() {
            modal.style.display = 'flex';
        });

        modalCancel.addEventListener('click', function() {
            modal.style.display = 'none';
        });

        modalConfirm.addEventListener('click', function() {
            modal.style.display = 'none';
            if (formularioAutoexclusion) {
                formularioAutoexclusion.submit();
            }
        });
    }
});