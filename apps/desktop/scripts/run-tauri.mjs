import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
const env = { ...process.env };

const userProfile = env.USERPROFILE ?? "";
const cargoBin = join(userProfile, ".cargo", "bin");
if (existsSync(cargoBin)) {
  env.PATH = `${cargoBin};${env.PATH ?? ""}`;
}

const command = process.platform === "win32" ? "tauri.cmd" : "tauri";
const child = spawn(command, args, {
  stdio: "inherit",
  env,
  shell: process.platform === "win32",
});

child.on("error", (error) => {
  console.error(`[ERR] Failed to launch Tauri CLI: ${error.message}`);
  process.exit(1);
});

child.on("exit", (code) => {
  process.exit(code ?? 1);
});
