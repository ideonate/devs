import * as vscode from 'vscode';
import * as fs from 'fs/promises';
import * as path from 'path';
import { URL } from 'url';

const BRIDGE_CONTAINER_DIR = '/home/node/bridge';
const DROPPED_SUBDIR = 'dropped';
const HISTORY_KEY = 'devsBridge.history';
const HISTORY_LIMIT = 50;
// Downloads travel to the webview as one base64 message; past this size ask
// before tying up the window, and suggest scp instead.
const DOWNLOAD_WARN_BYTES = 200 * 1024 * 1024;
// Written into the bridge dir by `devs` on the host (see write_bridge_info in
// devs_common/utils/devcontainer.py).
const BRIDGE_INFO_FILE = '.devs-bridge.json';

interface HostInfo {
    hostPath: string;
    hostname: string | null;
}

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
    type: 'dropFiles' | 'dropUris' | 'copy' | 'reveal' | 'clear' | 'ready' | 'debug' | 'pickFiles' | 'sendToTerminal' | 'download';
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
    private hostInfo?: Promise<HostInfo | null>;

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
                await this.postHistory();
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
                // Open in an editor rather than revealInExplorer: the bridge dir is
                // outside the workspace, where reveal silently does nothing.
                // vscode.open picks the right editor (image preview, binary prompt).
                if (msg.path) {
                    await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(msg.path));
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
            case 'download':
                if (msg.path) {
                    await this.download(msg.path);
                }
                return;
            case 'debug':
                if (msg.message) {
                    vscode.window.showWarningMessage(`Bridge: ${msg.message}`);
                }
                return;
        }
    }

    // The webview runs wherever the VS Code UI runs (e.g. the laptop, when the
    // container is reached over Remote-SSH), and webviews may start downloads.
    // Handing it the bytes lets the browser save them via the local Save dialog.
    private async download(containerPath: string) {
        const stat = await fs.stat(containerPath);
        if (stat.size > DOWNLOAD_WARN_BYTES) {
            const choice = await vscode.window.showWarningMessage(
                `${path.basename(containerPath)} is ${Math.round(stat.size / (1024 * 1024))} MB. Downloading it through VS Code may be slow; scp is faster for large files.`,
                'Download anyway',
            );
            if (choice !== 'Download anyway') return;
        }
        const buf = await fs.readFile(containerPath);
        const name = path.basename(containerPath).replace(/^\d{8}-\d{6}(?:-\d+)?-/, '');
        this.view?.webview.postMessage({ type: 'download', name, dataBase64: buf.toString('base64') });
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

    // DEVS_BRIDGE_MOUNT_PATH comes from remoteEnv, which only the Dev Containers
    // extension applies. Over Remote-SSH into the container it is unset, so fall
    // back to the info file devs leaves in the bridge dir. Re-read until found,
    // so running `devs start` on the host fixes an open window without a reload.
    private getHostInfo(): Promise<HostInfo | null> {
        if (!this.hostInfo) {
            this.hostInfo = this.loadHostInfo().then((info) => {
                if (!info) this.hostInfo = undefined;
                return info;
            });
        }
        return this.hostInfo;
    }

    private async loadHostInfo(): Promise<HostInfo | null> {
        let fromFile: { host_path?: unknown; hostname?: unknown } = {};
        try {
            fromFile = JSON.parse(await fs.readFile(path.join(BRIDGE_CONTAINER_DIR, BRIDGE_INFO_FILE), 'utf8'));
        } catch {
            // Missing or unreadable: rely on the env var alone.
        }
        const hostPath = process.env.DEVS_BRIDGE_MOUNT_PATH
            || (typeof fromFile.host_path === 'string' ? fromFile.host_path : '');
        if (!hostPath) return null;
        const hostname = typeof fromFile.hostname === 'string' && fromFile.hostname ? fromFile.hostname : null;
        return { hostPath, hostname };
    }

    private async hostPathFor(containerPath: string): Promise<string | null> {
        const info = await this.getHostInfo();
        if (!info) return null;
        const rel = path.relative(BRIDGE_CONTAINER_DIR, containerPath);
        if (rel.startsWith('..')) return null;
        return path.join(info.hostPath, rel);
    }

    private async recordAndNotify(name: string, containerPath: string, origin: 'host' | 'container', size: number) {
        const hostPath = await this.hostPathFor(containerPath);
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

        await this.postEntry(entry);
    }

    private getHistory(): DropEntry[] {
        return this.context.workspaceState.get<DropEntry[]>(HISTORY_KEY, []);
    }

    async clearHistory() {
        await this.context.workspaceState.update(HISTORY_KEY, []);
        await this.postHistory();
    }

    private async postHistory() {
        // Entries recorded before the host path was known were stored with null.
        const entries = await Promise.all(this.getHistory().map(async (e) =>
            e.hostPath ? e : { ...e, hostPath: await this.hostPathFor(e.containerPath) }));
        const hostname = (await this.getHostInfo())?.hostname ?? null;
        this.view?.webview.postMessage({ type: 'history', entries, hostname });
    }

    private async postEntry(entry: DropEntry) {
        const hostname = (await this.getHostInfo())?.hostname ?? null;
        this.view?.webview.postMessage({ type: 'entry', entry, hostname });
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
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" content="${csp}">
    <link rel="stylesheet" href="${styleUri}">
</head>
<body>
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
