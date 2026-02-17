import { spawnSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";

function runCheck(command, args) {
  const result = spawnSync(command, args, {
    encoding: "utf-8",
    shell: process.platform === "win32",
  });
  const ok = result.status === 0;
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
  return { ok, output };
}

function runPathCheck(executablePath, args) {
  const result = spawnSync(executablePath, args, {
    encoding: "utf-8",
    shell: false,
  });
  const ok = result.status === 0;
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
  return { ok, output };
}

function printResult(name, ok, output, hint) {
  const marker = ok ? "[OK]" : "[ERR]";
  console.log(`${marker} ${name}`);
  if (output) {
    const firstLine = output.split(/\r?\n/)[0];
    console.log(`      ${firstLine}`);
  }
  if (!ok && hint) {
    console.log(`      Hint: ${hint}`);
  }
}

function windowsMsvcLinkerInstalled() {
  const candidates = [
    "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Tools\\MSVC",
    "C:\\Program Files\\Microsoft Visual Studio\\2022\\BuildTools\\VC\\Tools\\MSVC",
    "C:\\Program Files (x86)\\Microsoft Visual Studio\\2019\\BuildTools\\VC\\Tools\\MSVC",
  ];

  for (const base of candidates) {
    if (!existsSync(base)) {
      continue;
    }
    const versions = readdirSync(base, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
    for (const version of versions) {
      const linker = join(base, version, "bin", "Hostx64", "x64", "link.exe");
      if (existsSync(linker)) {
        return linker;
      }
    }
  }
  return null;
}

function windowsKernel32LibInstalled() {
  const sdkLibRoot = "C:\\Program Files (x86)\\Windows Kits\\10\\Lib";
  if (!existsSync(sdkLibRoot)) {
    return null;
  }
  const versions = readdirSync(sdkLibRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()
    .reverse();
  for (const version of versions) {
    const kernelLib = join(sdkLibRoot, version, "um", "x64", "kernel32.lib");
    if (existsSync(kernelLib)) {
      return kernelLib;
    }
  }
  return null;
}

let failed = false;

const cargoBin = join(process.env.USERPROFILE ?? "", ".cargo", "bin");
const rustcPath = process.platform === "win32" ? join(cargoBin, "rustc.exe") : join(cargoBin, "rustc");
const cargoPath = process.platform === "win32" ? join(cargoBin, "cargo.exe") : join(cargoBin, "cargo");

const rustc = runCheck("rustc", ["--version"]);
if (rustc.ok) {
  printResult("rustc", true, rustc.output, "");
} else if (existsSync(rustcPath)) {
  const rustcDirect = runPathCheck(rustcPath, ["--version"]);
  printResult("rustc", rustcDirect.ok, rustcDirect.output || rustc.output, "Install Rust via https://rustup.rs/");
  failed ||= !rustcDirect.ok;
} else {
  printResult("rustc", false, rustc.output, "Install Rust via https://rustup.rs/");
  failed = true;
}

const cargo = runCheck("cargo", ["--version"]);
if (cargo.ok) {
  printResult("cargo", true, cargo.output, "");
} else if (existsSync(cargoPath)) {
  const cargoDirect = runPathCheck(cargoPath, ["--version"]);
  printResult("cargo", cargoDirect.ok, cargoDirect.output || cargo.output, "Install Rust via https://rustup.rs/");
  failed ||= !cargoDirect.ok;
} else {
  printResult("cargo", false, cargo.output, "Install Rust via https://rustup.rs/");
  failed = true;
}

if (process.platform === "win32") {
  const linkerPath = windowsMsvcLinkerInstalled();
  const linkerOk = Boolean(linkerPath);
  printResult(
    "msvc-linker",
    linkerOk,
    linkerPath ?? "",
    "Install Visual Studio Build Tools with Desktop C++ workload.",
  );
  failed ||= !linkerOk;

  const kernelLibPath = windowsKernel32LibInstalled();
  const sdkOk = Boolean(kernelLibPath);
  printResult(
    "windows-sdk",
    sdkOk,
    kernelLibPath ?? "",
    "Install Windows 10 SDK (10.0.18362 or newer).",
  );
  failed ||= !sdkOk;
}

const keyvox = runCheck("keyvox", ["--help"]);
if (keyvox.ok) {
  printResult("keyvox", true, keyvox.output, "");
} else {
  const keyvoxPython = runCheck("python", ["-m", "keyvox", "--help"]);
  const keyvoxOk = keyvoxPython.ok;
  printResult(
    "keyvox",
    keyvoxOk,
    keyvoxOk ? "resolved via `python -m keyvox --help`" : keyvox.output,
    "Install Keyvox on PATH, or set a full executable path in Desktop -> Backend Command.",
  );
  failed ||= !keyvoxOk;
}

if (failed) {
  console.error("[ERR] Desktop doctor failed.");
  process.exit(1);
}

console.log("[OK] Desktop doctor passed.");
