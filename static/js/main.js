// Logica frontend adattata per usare l'API Flask /api/analyze

let emails = [];
let categoriaSelezionata = 'tutte';
let termineRicerca = '';

const emailForm = document.getElementById('emailForm');
const mittenteInput = document.getElementById('mittente');
const destinatarioInput = document.getElementById('destinatario');
const messaggioInput = document.getElementById('messaggio');
const charCount = document.getElementById('charCount');
const inviaBtn = document.getElementById('inviaBtn');
const resetBtn = document.getElementById('resetBtn');
const risultatiAnalisi = document.getElementById('risultatiAnalisi');
const categoriaSpan = document.getElementById('categoria');
const paroleChiaveDiv = document.getElementById('paroleChiave');
const riassuntoP = document.getElementById('riassunto');
const ricercaInput = document.getElementById('ricerca');
const pulisciRicerca = document.getElementById('pulisciRicerca');
const conteggioEmail = document.getElementById('conteggioEmail');
const listaEmail = document.getElementById('listaEmail');
const nessunaEmail = document.getElementById('nessunaEmail');
const categoriaBtns = document.querySelectorAll('.categoria-btn');
const modaleEmail = document.getElementById('modaleEmail');
const chiudiModale = document.getElementById('chiudiModale');
const chiudiModale2 = document.getElementById('chiudiModale2');

function formattaData(data) {
	return new Intl.DateTimeFormat('it-IT', {
		month: 'short',
		day: 'numeric',
		hour: '2-digit',
		minute: '2-digit',
	}).format(data);
}

function creaBadgeCategoria(categoria) {
	const colori = {
		Lavoro: 'bg-blue-100 text-blue-800',
		Personale: 'bg-green-100 text-green-800',
		Promozionale: 'bg-purple-100 text-purple-800',
		Importante: 'bg-red-100 text-red-800',
		Newsletter: 'bg-yellow-100 text-yellow-800',
		Altro: 'bg-gray-100 text-gray-800',
	};
	return `<span class="px-2 py-1 rounded text-xs ${colori[categoria] || 'bg-gray-100 text-gray-800'}">${categoria}</span>`;
}

function creaBadgeParolaChiave(parola) {
	return `<span class="px-2 py-1 bg-gray-200 rounded text-sm">${parola}</span>`;
}

function aggiungiEmail(email) {
	const emailElement = document.createElement('div');
	emailElement.className = 'border rounded-lg p-4 hover:shadow-md transition cursor-pointer email-item';
	emailElement.dataset.id = email.id;

	emailElement.innerHTML = `
		<div class="flex items-start justify-between">
			<div class="flex-1">
				<div class="flex items-center gap-2">
					<h3 class="font-medium text-gray-900">${email.mittente} → ${email.destinatario}</h3>
					${creaBadgeCategoria(email.categoria || 'Altro')}
				</div>
				<p class="mt-1 text-sm text-gray-600 line-clamp-2">${email.riassunto}</p>
				<div class="mt-2 flex flex-wrap gap-1">
					${(email.paroleChiave || []).slice(0, 3).map((p) => creaBadgeParolaChiave(p)).join('')}
				</div>
			</div>
			<div class="ml-2 text-xs text-gray-500">${formattaData(email.timestamp)}</div>
		</div>
	`;

	emailElement.addEventListener('click', () => mostraDettagliEmail(email));
	listaEmail.insertBefore(emailElement, listaEmail.firstChild);
}

function mostraDettagliEmail(email) {
	document.getElementById('dettaglioMittente').textContent = email.mittente;
	document.getElementById('dettaglioDestinatario').textContent = email.destinatario;

	const dettaglioCategoria = document.getElementById('dettaglioCategoria');
	dettaglioCategoria.textContent = email.categoria || 'Altro';
	dettaglioCategoria.className = 'inline-block px-2 py-1 rounded text-xs mt-1';

	document.getElementById('dettaglioParoleChiave').innerHTML = (email.paroleChiave || [])
		.map((p) => creaBadgeParolaChiave(p))
		.join('');

	document.getElementById('dettaglioRiassunto').textContent = email.riassunto;
	document.getElementById('dettaglioMessaggio').textContent = email.messaggio;
	document.getElementById('dettaglioTimestamp').textContent = `Analizzata il ${formattaData(email.timestamp)}`;

	modaleEmail.classList.remove('hidden');
}

function aggiornaListaEmail() {
	let emailFiltrate = emails;

	if (termineRicerca) {
		const t = termineRicerca.toLowerCase();
		emailFiltrate = emailFiltrate.filter(
			(e) =>
				e.destinatario.toLowerCase().includes(t) ||
				e.mittente.toLowerCase().includes(t) ||
				(e.paroleChiave || []).some((p) => p.toLowerCase().includes(t)) ||
				(e.categoria || '').toLowerCase().includes(t) ||
				e.messaggio.toLowerCase().includes(t),
		);
	}

	if (categoriaSelezionata !== 'tutte') {
		emailFiltrate = emailFiltrate.filter((e) => (e.categoria || 'Altro') === categoriaSelezionata);
	}

	conteggioEmail.textContent = `${emailFiltrate.length} email`;
	document.querySelectorAll('.email-item').forEach((el) => el.remove());

	if (emailFiltrate.length === 0) {
		nessunaEmail.classList.remove('hidden');
		nessunaEmail.querySelector('p').textContent =
			termineRicerca || categoriaSelezionata !== 'tutte'
				? 'Nessuna email corrisponde ai tuoi filtri'
				: 'La tua cronologia email è vuota';
	} else {
		nessunaEmail.classList.add('hidden');
		emailFiltrate.forEach((e) => aggiungiEmail(e));
	}
}

emailForm.addEventListener('submit', async (e) => {
	e.preventDefault();

	const mittente = mittenteInput.value.trim();
	const destinatario = destinatarioInput.value.trim();
	const messaggio = messaggioInput.value.trim();
	if (!mittente || !destinatario || !messaggio) return;

	inviaBtn.disabled = true;
	inviaBtn.textContent = 'Analisi in corso...';

	try {
		const res = await fetch('/api/analyze', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ mittente, destinatario, messaggio }),
		});

		if (!res.ok) throw new Error('Errore API');

		const data = await res.json();

		const semantic = data.semantic || {};
		const routing = data.routing || {};
		const classification = data.classification || {};

		// Mappa i dati del backend su una categoria frontend (Lavoro, Promozionale, ecc.)
		function mappaCategoria(routing, classification) {
			if (classification.is_spam) return 'Promozionale';
			const dept = (routing.department || '').toUpperCase();
			if (dept === 'IT' || dept === 'HR' || dept === 'FINANCE' || dept === 'SALES') return 'Lavoro';
			if (dept === 'SUPPORT') return 'Importante';
			return 'Altro';
		}

		const categoria = mappaCategoria(routing, classification);

		const paroleChiave = [];
		if (semantic.intent) paroleChiave.push(semantic.intent);
		if (semantic.tone) paroleChiave.push(semantic.tone);
		if (semantic.urgency) paroleChiave.push(semantic.urgency);

		const riassunto = semantic.summary || (messaggio.length > 100 ? messaggio.slice(0, 100) + '...' : messaggio);

		const nuovaEmail = {
			id: Date.now().toString(),
			mittente,
			destinatario,
			messaggio,
			categoria,
			paroleChiave,
			riassunto,
			timestamp: new Date(),
		};

		emails.unshift(nuovaEmail);

		categoriaSpan.textContent = nuovaEmail.categoria;
		categoriaSpan.className = 'inline-block px-2 py-1 rounded text-xs bg-gray-500 text-white';

		paroleChiaveDiv.innerHTML = paroleChiave
			.map((p) => `<span class="px-2 py-1 bg-gray-200 rounded text-sm">${p}</span>`)
			.join(' ');

		riassuntoP.textContent = riassunto;
		risultatiAnalisi.classList.remove('hidden');

		aggiornaListaEmail();
	} catch (err) {
		alert('Errore durante l\'analisi dell\'email');
		console.error(err);
	} finally {
		inviaBtn.disabled = false;
		inviaBtn.textContent = 'Invia e Analizza';
	}
});

resetBtn.addEventListener('click', () => {
	emailForm.reset();
	charCount.textContent = '0';
	risultatiAnalisi.classList.add('hidden');
});

messaggioInput.addEventListener('input', function () {
	charCount.textContent = this.value.length;
});

ricercaInput.addEventListener('input', function () {
	termineRicerca = this.value.trim();
	pulisciRicerca.classList.toggle('hidden', !termineRicerca);
	aggiornaListaEmail();
});

pulisciRicerca.addEventListener('click', () => {
	ricercaInput.value = '';
	termineRicerca = '';
	pulisciRicerca.classList.add('hidden');
	aggiornaListaEmail();
});

categoriaBtns.forEach((btn) => {
	btn.addEventListener('click', function () {
		categoriaBtns.forEach((b) => {
			b.classList.remove('bg-indigo-600', 'text-white', 'active');
			b.classList.add('border');
		});
		this.classList.remove('border');
		this.classList.add('bg-indigo-600', 'text-white', 'active');
		categoriaSelezionata = this.dataset.categoria;
		aggiornaListaEmail();
	});
});

chiudiModale.addEventListener('click', () => modaleEmail.classList.add('hidden'));
chiudiModale2.addEventListener('click', () => modaleEmail.classList.add('hidden'));

modaleEmail.addEventListener('click', (e) => {
	if (e.target === modaleEmail) modaleEmail.classList.add('hidden');
});

document.addEventListener('DOMContentLoaded', () => {
	risultatiAnalisi.classList.add('hidden');
});
