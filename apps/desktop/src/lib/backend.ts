import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

export interface BackendStatus {
  running: boolean;
  port: number | null;
  managed: boolean;
}

export interface BackendPreflight {
  ok: boolean;
  backendCommand: string;
  executableFound: boolean;
  portValid: boolean;
  issueCode: string | null;
  message: string;
}

export async function backendStatus(): Promise<BackendStatus> {
  return invoke<BackendStatus>("backend_status");
}

export async function backendPreflight(preferredPort: number, command?: string): Promise<BackendPreflight> {
  return invoke<BackendPreflight>("backend_preflight", {
    preferredPort,
    command,
  });
}

export async function startBackend(preferredPort: number, command?: string): Promise<BackendStatus> {
  return invoke<BackendStatus>("start_backend", {
    preferredPort,
    command,
  });
}

export async function stopBackend(): Promise<BackendStatus> {
  return invoke<BackendStatus>("stop_backend");
}

export async function pickStorageFolder(): Promise<string | null> {
  return invoke<string | null>("pick_storage_folder");
}

export async function setTrayStatus(tooltip: string): Promise<void> {
  await invoke("set_tray_status", { tooltip });
}

export interface NvidiaInfo {
  gpuName: string;
  cudaVersion: string;
}

export async function getDefaultInstallDir(): Promise<string> {
  return invoke<string>("get_default_install_dir");
}

export async function detectNvidia(): Promise<NvidiaInfo | null> {
  return invoke<NvidiaInfo | null>("detect_nvidia");
}

export async function installBackend(
  stack: "gpu" | "cpu",
  installDir: string,
  onProgress: (line: string) => void,
): Promise<void> {
  const unlisten = await listen<string>("backend-install-progress", (e) => {
    onProgress(e.payload);
  });
  try {
    await invoke("install_backend", { stack, installDir });
  } finally {
    unlisten();
  }
}
