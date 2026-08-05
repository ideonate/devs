// Writes extensions.json so VS Code SSH remote discovers pre-installed extensions.
// VS Code trusts this registry rather than scanning the directory.
const fs = require("fs");
const path = require("path");

const extDir = "/home/node/.vscode-server/extensions";

const entries = fs
  .readdirSync(extDir)
  .filter(
    (d) =>
      !d.endsWith(".json") && fs.statSync(path.join(extDir, d)).isDirectory(),
  )
  .flatMap((dir) => {
    try {
      const pkg = JSON.parse(
        fs.readFileSync(path.join(extDir, dir, "package.json"), "utf8"),
      );
      return [
        {
          identifier: { id: `${pkg.publisher}.${pkg.name}` },
          version: pkg.version,
          location: { $mid: 1, path: path.join(extDir, dir), scheme: "file" },
          relativeLocation: dir,
          metadata: { installedTimestamp: 1700000000000, source: "vsix" },
        },
      ];
    } catch (e) {
      return [];
    }
  });

fs.writeFileSync(path.join(extDir, "extensions.json"), JSON.stringify(entries));
