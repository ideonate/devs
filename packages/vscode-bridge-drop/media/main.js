(function () {
    const vscode = acquireVsCodeApi();
    const dropzone = document.getElementById('dropzone');
    const entriesEl = document.getElementById('entries');
    const clearBtn = document.getElementById('clear-btn');

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatSize(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
        return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
    }

    function formatTime(ts) {
        const d = new Date(ts);
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    function splitForEllipsis(name) {
        const dot = name.lastIndexOf('.');
        if (dot > 0 && name.length - dot <= 10) {
            return { head: name.slice(0, dot), tail: name.slice(dot) };
        }
        if (name.length > 16) {
            return { head: name.slice(0, -6), tail: name.slice(-6) };
        }
        return { head: name, tail: '' };
    }

    function displayName(rawName) {
        return rawName.replace(/^\d{8}-\d{6}(?:-\d+)?-/, '');
    }

    // Name of the docker host, so a UI running on another machine (e.g. over
    // Remote-SSH) makes clear which machine the host path is on.
    let hostname = null;

    function renderEntry(entry) {
        const li = document.createElement('li');
        li.className = 'entry';
        const display = displayName(entry.name);
        const { head, tail } = splitForEllipsis(display);
        const dragHandle = (p) =>
            `<span class="drag-handle" draggable="true" data-path="${escapeHtml(p)}" title="Drag this path into an editor or host terminal">⠿</span>`;
        // A ready-to-paste command for a terminal on the machine running VS Code.
        const scpCommand = entry.hostPath && hostname
            ? `scp ${hostname}:${/\s/.test(entry.hostPath) ? `'${entry.hostPath.replace(/'/g, `'\\''`)}'` : entry.hostPath} .`
            : null;
        const scpAction = scpCommand
            ? `<button class="copy" data-path="${escapeHtml(scpCommand)}" data-label="scp" title="Copy: ${escapeHtml(scpCommand)}">scp</button>`
            : '';
        const hostActions = entry.hostPath
            ? `${dragHandle(entry.hostPath)}<button class="copy" data-path="${escapeHtml(entry.hostPath)}" title="Copy ${escapeHtml(entry.hostPath)}">Path</button>${scpAction}`
            : `<span class="unavail">unavailable</span>`;
        li.innerHTML = `
            <div class="entry-head">
                <div class="entry-title">
                    <div class="name-wrap" title="${escapeHtml(entry.name)}">
                        <span class="name-head">${escapeHtml(head)}</span><span class="name-tail">${escapeHtml(tail)}</span>
                    </div>
                    <div class="meta">${escapeHtml(entry.origin === 'host' ? 'from host' : 'from container')} · ${formatSize(entry.size)} · ${formatTime(entry.timestamp)}</div>
                </div>
                <button class="download" data-path="${escapeHtml(entry.containerPath)}" title="Save a copy on the machine running VS Code">Download</button>
            </div>
            <div class="actions">
                <span class="action-label">Container</span>
                ${dragHandle(entry.containerPath)}
                <button class="copy" data-path="${escapeHtml(entry.containerPath)}" title="Copy ${escapeHtml(entry.containerPath)}">Path</button>
                <button class="send" data-path="${escapeHtml(entry.containerPath)}" title="Send path to active VS Code terminal">Send</button>
                <button class="reveal" data-path="${escapeHtml(entry.containerPath)}" title="Open in a VS Code editor">Open</button>
            </div>
            <div class="actions">
                <span class="action-label" title="${escapeHtml(hostname ? `Path on docker host ${hostname}` : 'Path on docker host')}">${escapeHtml(hostname || 'Host')}</span>
                ${hostActions}
            </div>
        `;
        return li;
    }

    function renderAll(entries) {
        entriesEl.innerHTML = '';
        for (const e of entries) entriesEl.appendChild(renderEntry(e));
    }

    function prependEntry(entry) {
        const li = renderEntry(entry);
        entriesEl.insertBefore(li, entriesEl.firstChild);
    }

    entriesEl.addEventListener('click', (e) => {
        const target = e.target;
        if (!(target instanceof HTMLElement)) return;
        const p = target.dataset.path;
        if (!p) return;
        if (target.classList.contains('copy')) {
            vscode.postMessage({ type: 'copy', path: p });
            const label = target.dataset.label || 'Path';
            target.textContent = 'Copied';
            setTimeout(() => { target.textContent = label; }, 1200);
        } else if (target.classList.contains('reveal')) {
            vscode.postMessage({ type: 'reveal', path: p });
        } else if (target.classList.contains('download')) {
            vscode.postMessage({ type: 'download', path: p });
        } else if (target.classList.contains('send')) {
            vscode.postMessage({ type: 'sendToTerminal', path: p });
            target.textContent = 'Sent';
            setTimeout(() => { target.textContent = 'Send'; }, 1200);
        }
    });

    entriesEl.addEventListener('dragstart', (e) => {
        const target = e.target;
        if (!(target instanceof HTMLElement)) return;
        if (!target.classList.contains('drag-handle')) return;
        const p = target.dataset.path;
        if (!p || !e.dataTransfer) return;
        const quoted = /\s/.test(p) ? `'${p.replace(/'/g, `'\\''`)}'` : p;
        const fileUri = 'file://' + p.split('/').map(encodeURIComponent).join('/');
        e.dataTransfer.setData('text/plain', quoted);
        e.dataTransfer.setData('text/uri-list', fileUri);
        try { e.dataTransfer.setData('application/vnd.code.uri-list', fileUri); } catch {}
        e.dataTransfer.effectAllowed = 'all';
    });

    clearBtn.addEventListener('click', () => {
        vscode.postMessage({ type: 'clear' });
    });

    const pickBtn = document.getElementById('pick-btn');
    if (pickBtn) {
        pickBtn.addEventListener('click', () => {
            vscode.postMessage({ type: 'pickFiles' });
        });
    }

    function setActive(active) {
        dropzone.classList.toggle('active', active);
    }

    ['dragenter', 'dragover'].forEach((ev) => {
        dropzone.addEventListener(ev, (e) => {
            e.preventDefault();
            e.stopPropagation();
            setActive(true);
        });
    });
    ['dragleave', 'drop'].forEach((ev) => {
        dropzone.addEventListener(ev, (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (ev === 'dragleave' && e.target !== dropzone) return;
            setActive(false);
        });
    });

    async function fileToBase64(file) {
        const buf = await file.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = '';
        const chunk = 0x8000;
        for (let i = 0; i < bytes.length; i += chunk) {
            binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
        }
        return btoa(binary);
    }

    dropzone.addEventListener('drop', async (e) => {
        const dt = e.dataTransfer;
        if (!dt) return;

        const types = Array.from(dt.types || []);
        console.log('[bridge] drop types:', types);

        const fileList = dt.files;
        if (fileList && fileList.length > 0) {
            const files = [];
            for (const f of fileList) {
                files.push({ name: f.name, dataBase64: await fileToBase64(f) });
            }
            vscode.postMessage({ type: 'dropFiles', files });
            return;
        }

        const uriMimeCandidates = [
            'application/vnd.code.uri-list',
            'text/uri-list',
            'application/vnd.code.tree.explorer',
        ];
        let uriListRaw = '';
        for (const mime of uriMimeCandidates) {
            const v = dt.getData(mime);
            if (v) {
                uriListRaw = v;
                break;
            }
        }
        if (!uriListRaw) {
            const plain = dt.getData('text/plain');
            if (plain && (plain.startsWith('file://') || plain.startsWith('/'))) {
                uriListRaw = plain;
            }
        }

        if (uriListRaw) {
            const uris = uriListRaw.split(/\r?\n/).filter((u) => u && !u.startsWith('#'));
            if (uris.length > 0) {
                vscode.postMessage({ type: 'dropUris', uris });
                return;
            }
        }

        vscode.postMessage({
            type: 'debug',
            message: `No usable drop data. MIME types present: ${types.join(', ') || '(none)'}`,
        });
    });

    function saveLocally(name, dataBase64) {
        const binary = atob(dataBase64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
        const url = URL.createObjectURL(new Blob([bytes]));
        const a = document.createElement('a');
        a.href = url;
        a.download = name || 'download';
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    }

    window.addEventListener('message', (event) => {
        const msg = event.data;
        if (!msg || typeof msg !== 'object') return;
        if ('hostname' in msg) hostname = msg.hostname || null;
        if (msg.type === 'history') renderAll(msg.entries || []);
        if (msg.type === 'entry' && msg.entry) prependEntry(msg.entry);
        if (msg.type === 'download' && msg.dataBase64) saveLocally(msg.name, msg.dataBase64);
    });

    vscode.postMessage({ type: 'ready' });
})();
