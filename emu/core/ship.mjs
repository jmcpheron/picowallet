// Put a module on the real Pico and run it. Used by `tools/emu ship NAME` and the page's
// "send to Pico" button (server route /ctl/ship).
//   ship(name, { target: "usb" | "wifi", port }) -> { ok, port, lines, blocking, error? }
// usb: `port` from the device picker, else the first /dev/cu.usbmodem* (mac) or /dev/ttyACM* (linux). wifi: the wallet Pico's
// socket console (PICO_HOST, default picowallet.local:2323), same as tools/pico.
// The module is copied (lcd.py too if the board lacks it), the board is soft-reset (USB), then the
// module is imported with the same snippet the emulator uses. Output is followed for a few seconds; a module that never returns
// (a `while True`) is reported as blocking and left running.
import { spawn } from "node:child_process";
import { join } from "node:path";
import { FIRMWARE, SKETCHES, listWorkspace, entryFor } from "./workspace.mjs";
import { runCode } from "./runtime.mjs";
import { MPREMOTE, lock, serialPorts } from "./devices.mjs";

const FOLLOW_MS = 4000;

export function findUsbPort() { return serialPorts()[0] || null; }

// resume=false lets mpremote soft-reset first: every timer from the last module dies, and main.py
// does not run again (raw REPL skips it). That is what makes a send replace what is on the screen.
function mp(port, args, timeoutMs, resume = true) {
  return new Promise((resolve) => {
    const child = spawn(MPREMOTE, ["connect", port, ...(resume ? ["resume"] : []), ...args], { stdio: ["ignore", "pipe", "pipe"] });
    let out = "", done = false;
    const finish = (code, killed) => { if (done) return; done = true; resolve({ code, killed, out }); };
    child.stdout.on("data", (d) => (out += d));
    child.stderr.on("data", (d) => (out += d));
    child.on("error", (e) => { out += String(e); finish(1, false); });
    child.on("exit", (c) => finish(c, false));
    setTimeout(() => { if (!done) { child.kill("SIGKILL"); finish(null, true); } }, timeoutMs);
  });
}

const lines = (s) => s.replace(/\r/g, "").split("\n").map((l) => l.trimEnd()).filter(Boolean);

export async function ship(name, opts = {}) {
  name = name.replace(/\.py$/, "").replace(/^.*\//, "");
  const file = listWorkspace().find((f) => f.name === name + ".py");
  if (!file) return { ok: false, error: `no module ${name}.py in firmware/ or emu/sketches/` };
  const src = join(file.src === "firmware" ? FIRMWARE : SKETCHES, file.name);
  const target = opts.target || "usb";
  const port = target === "wifi" ? `socket://${process.env.PICO_HOST || "picowallet.local"}:2323` : (opts.port || findUsbPort());
  if (!port) return { ok: false, error: "no Pico on USB (nothing at /dev/cu.usbmodem*); plug one in, or ship --wifi" };
  if (opts.port && target !== "wifi" && !serialPorts().includes(opts.port)) return { ok: false, error: "no board at " + opts.port + " any more" };

  for (let i = 0; i < 20 && lock.busy; i++) await new Promise((r) => setTimeout(r, 500));
  lock.busy = true;
  try { return await doShip(name, file, src, port, target); } finally { lock.busy = false; }
}

async function doShip(name, file, src, port, target) {
  const ls = await mp(port, ["exec", "import os; print(os.listdir())"], 15000);
  if (ls.code !== 0) return { ok: false, port, error: "cannot talk to the Pico at " + port, lines: lines(ls.out) };
  const have = ls.out.includes("'lcd.py'");

  const args = [];
  if (!have) args.push("cp", join(FIRMWARE, "lcd.py"), ":lcd.py", "+");
  args.push("cp", src, `:${file.name}`, "+", "exec", runCode(name, entryFor(name)));
  // USB: soft reset for a clean slate. WiFi wallet: a soft reset would rerun boot.py and drop the
  // console, so keep resume there; runCode stops the old copy of the module instead.
  const r = await mp(port, args, FOLLOW_MS, target === "wifi");
  const out = lines(r.out);
  const failed = out.some((l) => /^Traceback/.test(l));
  return { ok: !failed && (r.killed || r.code === 0), port, blocking: r.killed, copiedLcd: !have, lines: out };
}
