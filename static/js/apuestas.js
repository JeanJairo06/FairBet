const ticketItems = document.getElementById('ticket-items');
const formularioTicket = document.getElementById('bet-slip');
const ticketVacio = document.getElementById('ticket-empty');
const ticketContenido = document.getElementById('ticket-content');
const ticketOdds = document.getElementById('ticket-odds');
const ticketPayout = document.getElementById('ticket-payout');
const stakeInput = document.getElementById('ticket-stake');
const ticketLimits = document.getElementById('ticket-limits');
const ticketCounter = document.getElementById('ticket-counter');
const MAX_SELECCIONES = 30;

let selecciones = [];

function leerDecimal(valor) {
    return Number(String(valor || '0').replace(',', '.'));
}

function mostrarDecimal(valor) {
    return leerDecimal(valor).toFixed(2);
}

function oddsCombinada() {
    if (selecciones.length === 0) return 1;
    return selecciones.reduce((prod, s) => prod * leerDecimal(s.odds), 1);
}

function actualizarCounter() {
    if (!ticketCounter) return;
    const count = selecciones.length;
    ticketCounter.textContent = `${count}/${MAX_SELECCIONES}`;
    ticketCounter.classList.toggle('has-items', count > 0);
}

function actualizarTicket() {
    actualizarCounter();

    ticketVacio.hidden = selecciones.length > 0;
    ticketContenido.hidden = selecciones.length === 0;
    if (selecciones.length === 0) return;

    ticketItems.innerHTML = selecciones.map((s, i) =>
        `<div class="ticket-item">
            <div class="ticket-item__top">
                <span class="ticket-item__evento">${s.evento}</span>
                <button type="button" class="ticket-item__rm" data-idx="${i}" aria-label="Quitar">&times;</button>
            </div>
            <div class="ticket-item__detail">
                <span>${s.mercado} &middot; ${s.seleccion}</span>
                <strong>${mostrarDecimal(s.odds)}</strong>
            </div>
        </div>`
    ).join('');

    ticketItems.querySelectorAll('.ticket-item__rm').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx, 10);
            const sel = selecciones[idx];
            selecciones.splice(idx, 1);
            document.querySelectorAll('.odd-button').forEach(b => {
                if (b.dataset.seleccionId === sel.seleccionId) b.classList.remove('is-selected');
            });
            actualizarTicket();
        });
    });

    const comb = oddsCombinada();
    ticketOdds.textContent = mostrarDecimal(comb);

    const stake = leerDecimal(stakeInput.value);
    ticketPayout.textContent = stake > 0 ? mostrarDecimal(stake * comb) : '0.00';
}

document.addEventListener('click', (event) => {
    const boton = event.target.closest('.odd-button');
    if (!boton || boton.disabled) return;

    const id = boton.dataset.seleccionId;
    const mercadoId = boton.dataset.mercadoId || null;
    const idx = selecciones.findIndex(s => s.seleccionId === id);

    if (idx !== -1) {
        selecciones.splice(idx, 1);
        boton.classList.remove('is-selected');
    } else {
        if (mercadoId) {
            const idxMismoMercado = selecciones.findIndex(s => s.mercadoId === mercadoId);
            if (idxMismoMercado !== -1) {
                const anterior = selecciones[idxMismoMercado];
                document.querySelectorAll(`.odd-button[data-seleccion-id="${anterior.seleccionId}"]`)
                    .forEach(b => b.classList.remove('is-selected'));
                selecciones.splice(idxMismoMercado, 1);
            }
        }

        if (selecciones.length >= MAX_SELECCIONES) {
            alert(`Maximo ${MAX_SELECCIONES} selecciones por cupon.`);
            return;
        }

        selecciones.push({
            seleccionId: id,
            mercadoId,
            evento: boton.dataset.evento,
            mercado: boton.dataset.mercado,
            seleccion: boton.dataset.seleccion,
            odds: boton.dataset.odds,
            min: boton.dataset.min,
            max: boton.dataset.max,
        });
        boton.classList.add('is-selected');
    }
    actualizarTicket();
});

if (stakeInput) {
    stakeInput.addEventListener('input', () => {
        actualizarTicket();
    });
}

document.querySelectorAll('.quick-stakes button').forEach(boton => {
    boton.addEventListener('click', () => {
        stakeInput.value = boton.dataset.stake;
        actualizarTicket();
    });
});

if (formularioTicket) {
    formularioTicket.addEventListener('submit', (event) => {
        if (selecciones.length === 0) {
            event.preventDefault();
            ticketVacio.hidden = false;
            ticketContenido.hidden = true;
            return;
        }
        const ids = selecciones.map(s => s.seleccionId);
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'seleccion_ids';
        input.value = ids.join(',');
        formularioTicket.appendChild(input);
    });
}
