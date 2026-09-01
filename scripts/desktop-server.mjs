import { createServer } from "node:http";
import { exec } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const siteRoot = path.join(projectRoot, "desktop-dist");
const host = "127.0.0.1";
const configuredPort = Number(process.env.XIAOZHANGBEN_PORT || 32145);
const port = Number.isInteger(configuredPort) && configuredPort > 0 && configuredPort <= 65535 ? configuredPort : 32145;
const appUrl = `http://localhost:${port}`;
const healthUrl = `http://${host}:${port}`;
const heartbeatTimeout = 100_000;
const firstHeartbeatTimeout = 120_000;
const closeGrace = 4_000;
const startedAt = Date.now();
let lastHeartbeat = 0;
let closeTimer;

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".json": "application/json; charset=utf-8",
};

function openAppWindow() {
  if (process.env.XIAOZHANGBEN_NO_OPEN === "1" || process.argv.includes("--no-open")) return;
  exec(`start "" "${appUrl}"`, { windowsHide: true });
}

async function alreadyRunning() {
  try {
    const response = await fetch(`${healthUrl}/api/health`, { signal: AbortSignal.timeout(900) });
    if (!response.ok) return false;
    const data = await response.json();
    return data?.app === "xiaozhangben";
  } catch { return false; }
}

function stop() {
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1000).unref();
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || "/", appUrl);
  if (request.method === "POST" && url.pathname === "/api/heartbeat") {
    lastHeartbeat = Date.now();
    if (closeTimer) { clearTimeout(closeTimer); closeTimer = undefined; }
    response.writeHead(204).end();
    return;
  }
  if (request.method === "POST" && url.pathname === "/api/bye") {
    response.writeHead(204).end();
    if (!closeTimer) closeTimer = setTimeout(stop, closeGrace);
    return;
  }
  if (request.method === "GET" && url.pathname === "/api/health") {
    response.writeHead(200, { "content-type": "application/json" }).end('{"ok":true,"app":"xiaozhangben"}');
    return;
  }
  if (request.method !== "GET" && request.method !== "HEAD") {
    response.writeHead(405).end();
    return;
  }

  let requested;
  try { requested = url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname.slice(1)); }
  catch { response.writeHead(400).end(); return; }
  const filePath = path.resolve(siteRoot, requested);
  if (!filePath.startsWith(siteRoot + path.sep) && filePath !== path.join(siteRoot, "index.html")) {
    response.writeHead(403).end();
    return;
  }
  try {
    const data = await readFile(filePath);
    response.writeHead(200, { "content-type": mimeTypes[path.extname(filePath)] || "application/octet-stream", "cache-control": "no-store" });
    response.end(request.method === "HEAD" ? undefined : data);
  } catch {
    response.writeHead(404).end();
  }
});

if (await alreadyRunning()) {
  openAppWindow();
  process.exit(0);
}

server.listen(port, host, () => {
  server.ref();
  console.log(`Xiaozhangben ready at ${appUrl}`);
  openAppWindow();
});
server.on("error", error => { console.error(error); process.exit(1); });

setInterval(() => {
  const now = Date.now();
  if (lastHeartbeat === 0 && now - startedAt > firstHeartbeatTimeout) stop();
  if (lastHeartbeat > 0 && now - lastHeartbeat > heartbeatTimeout) stop();
}, 5000);

process.on("SIGINT", stop);
process.on("SIGTERM", stop);
