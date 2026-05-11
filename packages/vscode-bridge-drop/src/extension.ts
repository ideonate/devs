import * as vscode from 'vscode';
import * as fs from 'fs/promises';
import * as path from 'path';
import { URL } from 'url';

const BRIDGE_CONTAINER_DIR = '/home/node/bridge';
const DROPPED_SUBDIR = 'dropped';
const HISTORY_KEY = 'devsBridge.history';
const HISTORY_LIMIT = 50;

interface DropEntry {
    name: string;
    containerPath: string;
    hostPath: string | null;
    origin: 'host' | 'container';
    timestamp: number;
    size: number;
}

interface IncomingFile {
    name: string;
    dataBase64: string;
}

interface IncomingMessage {
    type: 'dropFiles' | 'dropUris' | 'copy' | 'reveal' | 'clear' | 'ready' | 'debug' | 'pickFiles' | 'sendToTerminal';
    files?: IncomingFile[];
    uris?: string[];
    path?: string;
    message?: string;
}

export function activate(context: vscode.ExtensionContext) {
    const provider = new BridgeViewProvider(context);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider('devsBridgeDrop', provider),
        vscode.commands.registerCommand('devsBridge.clearHistory', () => provider.clearHistory()),
        vscode.commands.registerCommand('devsBridge.openBridgeDir', async () => {
            const uri = vscode.Uri.file(path.join(BRIDGE_CONTAINER_DIR, DROPPED_SUBDIR));
            await vscode.commands.executeCommand('revealInExplorer', uri);
        }),
        vscode.commands.registerCommand('devsBridge.copyToBridge', async (uri?: vscode.Uri, uris?: vscode.Uri[]) => {
            const targets: vscode.Uri[] = (uris && uris.length > 0) ? uris : (uri ? [uri] : []);
            if (targets.length === 0) {
                const picked = await vscode.window.showOpenDialog({
                    canSelectFiles: true,
                    canSelectFolders: false,
                    canSelectMany: true,
                    openLabel: 'Copy to Bridge',
                });
                if (!picked || picked.length === 0) return;
                targets.push(...picked);
            }
            for (const t of targets) {
                await provider.copyToBridge(t);
            }
        })
    );
}

export function deactivate() {}

class BridgeViewProvider implements vscode.WebviewViewProvider {
    private view?: vscode.WebviewView;

    constructor(private readonly context: vscode.ExtensionContext) {}

    resolveWebviewView(view: vscode.WebviewView) {
        this.view = view;
        view.webview.options = {
            enableScripts: true,
            localResourceRoots: [vscode.Uri.joinPath(this.context.extensionUri, 'media')],
        };
        view.webview.html = this.renderHtml(view.webview);

        view.webview.onDidReceiveMessage(async (msg: IncomingMessage) => {
            try {
                await this.handleMessage(msg);
            } catch (err) {
                const message = err instanceof Error ? err.message : String(err);
                vscode.window.showErrorMessage(`Bridge drop failed: ${message}`);
            }
        });
    }

    private async handleMessage(msg: IncomingMessage) {
        switch (msg.type) {
            case 'ready':
                this.postHistory();
                return;
            case 'dropFiles':
                if (msg.files) {
                    for (const f of msg.files) {
                        await this.writeFromBytes(f.name, f.dataBase64, 'host');
                    }
                }
                return;
            case 'dropUris':
                if (msg.uris) {
                    for (const uri of msg.uris) {
                        await this.writeFromUri(uri);
                    }
                }
                return;
            case 'copy':
                if (msg.path) {
                    await vscode.env.clipboard.writeText(msg.path);
                    vscode.window.setStatusBarMessage(`Copied: ${msg.path}`, 2000);
                }
                return;
            case 'reveal':
                if (msg.path) {
                    const uri = vscode.Uri.file(msg.path);
                    try {
                        await vscode.commands.executeCommand('revealInExplorer', uri);
                    } catch {
                        await vscode.window.showTextDocument(uri);
                    }
                }
                return;
            case 'clear':
                await this.clearHistory();
                return;
            case 'pickFiles':
                await vscode.commands.executeCommand('devsBridge.copyToBridge');
                return;
            case 'sendToTerminal':
                if (msg.path) {
                    const term = vscode.window.activeTerminal ?? vscode.window.createTerminal('Bridge');
                    term.show(true);
                    const text = /\s/.test(msg.path) ? `'${msg.path.replace(/'/g, `'\\''`)}'` : msg.path;
                    term.sendText(text, false);
                }
                return;
            case 'debug':
                if (msg.message) {
                    vscode.window.showWarningMessage(`Bridge: ${msg.message}`);
                }
                return;
        }
    }

    async copyToBridge(uri: vscode.Uri): Promise<void> {
        if (uri.scheme !== 'file') {
            vscode.window.showWarningMessage(`Bridge: unsupported scheme ${uri.scheme}`);
            return;
        }
        try {
            await this.writeFromUri(uri.fsPath);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            vscode.window.showErrorMessage(`Bridge copy failed: ${message}`);
        }
    }

    private async writeFromBytes(rawName: string, dataBase64: string, origin: 'host' | 'container') {
        const buf = Buffer.from(dataBase64, 'base64');
        const finalName = await this.uniqueName(rawName);
        const containerPath = path.join(BRIDGE_CONTAINER_DIR, DROPPED_SUBDIR, finalName);
        await this.ensureDir();
        await fs.writeFile(containerPath, buf);
        await this.recordAndNotify(finalName, containerPath, origin, buf.length);
    }

    private async writeFromUri(rawUri: string) {
        const sourcePath = rawUri.startsWith('file://') || rawUri.startsWith('/')
            ? this.uriToFsPath(rawUri)
            : rawUri;
        if (!sourcePath) {
            throw new Error(`Unsupported drop source: ${rawUri}`);
        }
        const stat = await fs.stat(sourcePath);
        if (!stat.isFile()) {
            throw new Error(`Folder drops not supported: ${sourcePath}`);
        }
        const finalName = await this.uniqueName(path.basename(sourcePath));
        const containerPath = path.join(BRIDGE_CONTAINER_DIR, DROPPED_SUBDIR, finalName);
        await this.ensureDir();
        await fs.copyFile(sourcePath, containerPath);
        await this.recordAndNotify(finalName, containerPath, 'container', stat.size);
    }

    private uriToFsPath(raw: string): string | null {
        const trimmed = raw.trim();
        if (!trimmed) return null;
        if (trimmed.startsWith('file://')) {
            try {
                return decodeURIComponent(new URL(trimmed).pathname);
            } catch {
                return null;
            }
        }
        if (trimmed.startsWith('/')) {
            return trimmed;
        }
        return null;
    }

    private async ensureDir() {
        await fs.mkdir(path.join(BRIDGE_CONTAINER_DIR, DROPPED_SUBDIR), { recursive: true });
    }

    private async uniqueName(rawName: string): Promise<string> {
        const sanitized = this.sanitize(rawName);
        const ts = this.timestamp();
        let candidate = `${ts}-${sanitized}`;
        let counter = 1;
        while (await this.exists(path.join(BRIDGE_CONTAINER_DIR, DROPPED_SUBDIR, candidate))) {
            candidate = `${ts}-${counter}-${sanitized}`;
            counter += 1;
        }
        return candidate;
    }

    private sanitize(name: string): string {
        const base = path.basename(name);
        return base.replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 120) || 'file';
    }

    private timestamp(): string {
        const d = new Date();
        const pad = (n: number) => String(n).padStart(2, '0');
        return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
    }

    private async exists(p: string): Promise<boolean> {
        try {
            await fs.access(p);
            return true;
        } catch {
            return false;
        }
    }

    private hostPathFor(containerPath: string): string | null {
        const hostBase = process.env.DEVS_BRIDGE_MOUNT_PATH;
        if (!hostBase) return null;
        const rel = path.relative(BRIDGE_CONTAINER_DIR, containerPath);
        if (rel.startsWith('..')) return null;
        return path.join(hostBase, rel);
    }

    private async recordAndNotify(name: string, containerPath: string, origin: 'host' | 'container', size: number) {
        const hostPath = this.hostPathFor(containerPath);
        const entry: DropEntry = {
            name,
            containerPath,
            hostPath,
            origin,
            timestamp: Date.now(),
            size,
        };
        const history = this.getHistory();
        history.unshift(entry);
        await this.context.workspaceState.update(HISTORY_KEY, history.slice(0, HISTORY_LIMIT));

        await vscode.env.clipboard.writeText(containerPath);
        vscode.window.setStatusBarMessage(`Bridge: copied path for ${name}`, 3000);

        this.postEntry(entry);
    }

    private getHistory(): DropEntry[] {
        return this.context.workspaceState.get<DropEntry[]>(HISTORY_KEY, []);
    }

    async clearHistory() {
        await this.context.workspaceState.update(HISTORY_KEY, []);
        this.postHistory();
    }

    private postHistory() {
        this.view?.webview.postMessage({ type: 'history', entries: this.getHistory() });
    }

    private postEntry(entry: DropEntry) {
        this.view?.webview.postMessage({ type: 'entry', entry });
    }

    private renderHtml(webview: vscode.Webview): string {
        const nonce = randomNonce();
        const mediaRoot = vscode.Uri.joinPath(this.context.extensionUri, 'media');
        const scriptUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaRoot, 'main.js'));
        const styleUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaRoot, 'main.css'));
        const csp = [
            `default-src 'none'`,
            `img-src ${webview.cspSource}`,
            `style-src ${webview.cspSource} 'unsafe-inline'`,
            `script-src 'nonce-${nonce}'`,
        ].join('; ');
        const hostBase = process.env.DEVS_BRIDGE_MOUNT_PATH ?? '';
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" content="${csp}">
    <link rel="stylesheet" href="${styleUri}">
</head>
<body data-host-base="${escapeAttr(hostBase)}">
    <div id="dropzone" tabindex="0">
        <div class="dz-title">Drop files here</div>
        <div class="dz-sub">From your host OS (drag from Finder / Explorer)</div>
    </div>
    <div class="pick-row">
        <button id="pick-btn" class="primary-btn">Add files from container…</button>
        <div class="hint">Or right-click any file in the explorer → "Copy to Bridge"</div>
    </div>
    <div class="header">
        <span class="header-title">Recent drops</span>
        <button id="clear-btn" class="link-btn">Clear</button>
    </div>
    <ul id="entries"></ul>
    <script nonce="${nonce}" src="${scriptUri}"></script>
</body>
</html>`;
    }
}

function randomNonce(): string {
    let s = '';
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 32; i += 1) {
        s += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return s;
}

function escapeAttr(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
