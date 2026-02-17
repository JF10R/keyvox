import { invoke } from "@tauri-apps/api/core";

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
