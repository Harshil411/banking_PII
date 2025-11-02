async function postJSON(url, body) {
	const res = await fetch(url, {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(body)
	});
	if (!res.ok) throw new Error(`HTTP ${res.status}`);
	return res.json();
}

async function getJSON(url) {
	const res = await fetch(url);
	if (!res.ok) throw new Error(`HTTP ${res.status}`);
	return res.json();
}

function pretty(obj) {
	try { return JSON.stringify(obj, null, 2); } catch { return String(obj); }
}

function bind() {
	const bertBtn = document.getElementById('bert-run');
	const bertText = document.getElementById('bert-text');
	const bertOut = document.getElementById('bert-output');

	const llamaBtn = document.getElementById('llama-run');
	const llamaText = document.getElementById('llama-text');
	const replacement = document.getElementById('replacement');
	const llamaOut = document.getElementById('llama-output');

	bertBtn?.addEventListener('click', async () => {
		bertOut.textContent = 'Running…';
		try {
			const data = await postJSON('/api/bert/extract', { text: bertText.value });
			bertOut.textContent = pretty(data);
		} catch (e) {
			bertOut.textContent = `Error: ${e.message}`;
		}
	});

	llamaBtn?.addEventListener('click', async () => {
		llamaOut.textContent = 'Running…';
		try {
			const data = await postJSON('/api/llama/anonymize', { text: llamaText.value, replacement: replacement.value });
			llamaOut.textContent = pretty(data);
		} catch (e) {
			llamaOut.textContent = `Error: ${e.message}`;
		}
	});
}

async function boot() {
	bind();
	try {
		const metrics = await getJSON('/api/metrics');
		document.getElementById('metrics').textContent = pretty(metrics);
	} catch (e) {
		document.getElementById('metrics').textContent = 'No metrics available.';
	}
	try {
		const schema = await getJSON('/api/data_schema');
		document.getElementById('schema').textContent = pretty(schema);
	} catch (e) {
		document.getElementById('schema').textContent = 'No data schema available.';
	}
}

boot();
