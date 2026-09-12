// Every Pico-like thing on USB, for the page's device picker and `tools/emu devices`.
//   listDevices() -> [{ kind: "serial", port, label, board? } | { kind: "bootsel", path, label, board }]
// serial: /dev/cu.usbmodem* (mac) or /dev/ttyACM* (linux), a board running MicroPython. The first
// time a port is seen it is asked what it is (os.uname().machine, one short mpremote call, cached).
// bootsel: a board plugged in with BOOTSEL held mounts as a drive (RPI-RP2 for RP2040, RP2350 for
// Pico 2) with INFO_UF2.TXT; it has no serial port and runs nothing until a .uf2 is copied on.
//   flash(path, { version }) downloads the MicroPython .uf2 for that board and copies it over.
import { readdirSync, readFileSync, existsSync, mkdirSync, writeFileSync, copyFileSync, statSync } from "node:fs";
import { spawn } from "node:child_process";
import { join } from "node:path";
import { homedir } from "node:os";

export const MPREMOTE = [join(homedir(), ".local/bin/mpremote"), "mpremote"].find((p) => !p.includes("/") || existsSync(p));
export const lock = { busy: false };                 // set while ship/identify holds a port
const known = new Map();                              // port -> { label, board } or "pending"
const UF2_DIR = join(homedir(), ".cache", "picowallet-uf2");
export const DEFAULT_MP_VERSION = process.env.MP_VERSION || "1.26.1";   // what the wallet Pico and the emulator run
const BOARD_UF2 = { "RP2350": "RPI_PICO2_W", "RPI-RP2": "RPI_PICO_W" };

export function serialPorts() {
  return readdirSync("/dev").filter((n) => /^cu\.usbmodem|^ttyACM/.test(n)).sort().map((n) => join("/dev", n));
}

export function bootselDrives() {
  const roots = ["/Volumes", join("/media", process.env.USER || ""), "/run/media/" + (process.env.USER || "")];
  const out = [];
  for (const root of roots) {
    if (!existsSync(root)) continue;
    for (const v of readdirSync(root)) {
      const info = join(root, v, "INFO_UF2.TXT");
      try { if (!statSync(info).isFile()) continue; } catch { continue; }
      const t = readFileSync(info, "utf8");
      const board = (t.match(/Board-ID:\s*(\S+)/) || [])[1] || "?";
      const model = (t.match(/Model:\s*(.+)/) || [])[1] || "";
      out.push({ kind: "bootsel", path: join(root, v), board, model: model.trim(), uf2: BOARD_UF2[board] || null,
        label: `${model.trim() || board} in bootloader (${v}) - needs MicroPython` });
    }
  }
  return out;
}

export function listDevices() {
  const out = [];
  for (const port of serialPorts()) {
    const k = known.get(port);
    if (!k) { known.set(port, "pending"); identify(port); }
    const short = port.replace(/^\/dev\/(cu\.)?/, "");
    out.push({ kind: "serial", port, board: k && k !== "pending" ? k.board : null,
      label: k && k !== "pending" ? `${k.board} · ${short}` : `${short} (MicroPython, identifying…)` });
  }
  return out.concat(bootselDrives());
}

export function forget(port) { known.delete(port); }

function run(cmd, args, timeoutMs) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"] });
    let out = "", done = false;
    const finish = (code, killed) => { if (done) return; done = true; resolve({ code, killed, out }); };
    child.stdout.on("data", (d) => (out += d)); child.stderr.on("data", (d) => (out += d));
    child.on("error", (e) => { out += String(e); finish(1, false); });
    child.on("exit", (c) => finish(c, false));
    setTimeout(() => { if (!done) { child.kill("SIGKILL"); finish(null, true); } }, timeoutMs);
  });
}

async function identify(port) {
  for (let i = 0; i < 20 && lock.busy; i++) await new Promise((r) => setTimeout(r, 500));
  if (lock.busy) { known.delete(port); return; }
  lock.busy = true;
  try {
    const r = await run(MPREMOTE, ["connect", port, "resume", "exec", "import os; print('MACHINE:', os.uname().machine)"], 8000);
    const m = r.out.match(/MACHINE:\s*(.+)/);
    const board = m ? m[1].trim().replace(/ with RP2\d+/, "") : "board";
    if (!serialPorts().includes(port)) known.delete(port);
    else known.set(port, { board, raw: r.out.trim() });
  } finally { lock.busy = false; }
}

// Newest stable MicroPython .uf2 for a board id from micropython.org (cached in ~/.cache).
export async function fetchUf2(uf2Board, version) {
  mkdirSync(UF2_DIR, { recursive: true });
  const want = version && version !== "latest" ? version : null;
  const cached = readdirSync(UF2_DIR).filter((f) => f.startsWith(uf2Board + "-") && f.endsWith(".uf2") && (!want || f.includes(`-v${want}.uf2`))).sort().at(-1);
  if (cached) return join(UF2_DIR, cached);
  const page = await (await fetch(`https://micropython.org/download/${uf2Board}/`)).text();
  const all = [...page.matchAll(new RegExp(`/resources/firmware/${uf2Board}-\\d{8}-v(\\d+\\.\\d+\\.\\d+)\\.uf2`, "g"))];
  if (!all.length) throw new Error("no stable .uf2 found on micropython.org for " + uf2Board);
  const hit = (want && all.find((m) => m[1] === want)) || all[0];
  const url = "https://micropython.org" + hit[0];
  const buf = Buffer.from(await (await fetch(url)).arrayBuffer());
  if (buf.length < 100000) throw new Error("download looks wrong: " + url);
  const file = join(UF2_DIR, hit[0].split("/").pop());
  writeFileSync(file, buf);
  return file;
}

export async function flash(path, opts = {}) {
  const d = bootselDrives().find((b) => b.path === path);
  if (!d) return { ok: false, error: "no bootloader drive at " + path };
  if (!d.uf2) return { ok: false, error: `no MicroPython build known for board ${d.board}` };
  const file = await fetchUf2(d.uf2, opts.version || DEFAULT_MP_VERSION);
  copyFileSync(file, join(d.path, "firmware.uf2"));   // the board reboots and unmounts as soon as it lands
  return { ok: true, file: file.split("/").pop(), board: d.uf2, note: "board reboots; it shows up as a serial port in a few seconds" };
}
