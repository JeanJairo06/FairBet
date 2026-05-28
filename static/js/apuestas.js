const botonesCuota = document.querySelectorAll('.odd-button');
const formularioTicket = document.getElementById('bet-slip');
const ticketVacio = document.getElementById('ticket-empty');
const ticketContenido = document.getElementById('ticket-content');
const seleccionInput = document.getElementById('ticket-seleccion-id');
const stakeInput = document.getElementById('ticket-stake');
const payoutText = document.getElementById('ticket-payout');
const oddsText = document.getElementById('ticket-odds');
let cuotaActual = 0;

function leerDecimal(valor) {
    return Number(String(valor || '0').replace(',', '.'));
}

function mostrarDecimal(valor) {
    return Number(valor || 0).toFixed(2);
}

function calcularPagoPotencial() {
    const stake = leerDecimal(stakeInput.value);
    const pago = stake > 0 ? stake * cuotaActual : 0;
    payoutText.textContent = mostrarDecimal(pago);
}

botonesCuota.forEach((boton) => {
    boton.addEventListener('click', () => {
        botonesCuota.forEach((item) => item.classList.remove('is-selected'));
        boton.classList.add('is-selected');

        cuotaActual = leerDecimal(boton.dataset.odds);
        seleccionInput.value = boton.dataset.seleccionId;
        document.getElementById('ticket-evento').textContent = boton.dataset.evento;
        document.getElementById('ticket-mercado').textContent = boton.dataset.mercado;
        document.getElementById('ticket-seleccion').textContent = boton.dataset.seleccion;
        oddsText.textContent = mostrarDecimal(cuotaActual);
        stakeInput.min = boton.dataset.min;
        stakeInput.max = boton.dataset.max;
        document.getElementById('ticket-limits').textContent = `Min ${boton.dataset.min} | Max ${boton.dataset.max}`;

        ticketVacio.hidden = true;
        ticketContenido.hidden = false;
        stakeInput.focus();
        calcularPagoPotencial();
    });
});

if (stakeInput) {
    stakeInput.addEventListener('input', calcularPagoPotencial);
}

document.querySelectorAll('.quick-stakes button').forEach((boton) => {
    boton.addEventListener('click', () => {
        stakeInput.value = boton.dataset.stake;
        calcularPagoPotencial();
    });
});

if (formularioTicket) {
    formularioTicket.addEventListener('submit', (event) => {
        if (!seleccionInput.value) {
            event.preventDefault();
            ticketVacio.hidden = false;
            ticketContenido.hidden = true;
        }
    });
}
