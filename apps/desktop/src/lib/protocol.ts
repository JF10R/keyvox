export interface ProtocolError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface ProtocolResponse {
  type: "response";
  protocol_version: string;
  timestamp: string;
  request_id: string | number | null;
  response_type: string;
  ok: boolean;
  result?: Record<string, unknown>;
  error?: ProtocolError;
}

export interface BackendCapability {
  id: string;
  label: string;
  available: boolean;
  requires: string[];
}

export interface ModelDownloadStatus {
  backend: string;
  name: string;
  downloaded: boolean | null;
}

export interface ModelRequirement {
  backend: string;
  name: string;
  estimated_total_bytes: number | null;
  already_present_bytes: number | null;
  remaining_bytes: number | null;
  disk_free_bytes: number | null;
  enough_space: boolean | null;
}

export interface StorageStatus {
  storage_root: string;
  effective_paths: Record<string, string>;
}

export interface CapabilitiesResult {
  backends: BackendCapability[];
  model_presets: Record<string, string[]>;
  model_devices: string[];
  compute_types: Record<string, string[]>;
  model_download_status: ModelDownloadStatus[];
  model_requirements: ModelRequirement[];
  active_model_download: { backend: string; name: string } | null;
  storage: StorageStatus;
  restart_policy: {
    hotkey: boolean;
    model: boolean;
    audio: boolean;
    dictionary: boolean;
    text_insertion: boolean;
  };
}

export interface AudioDeviceInfo {
  id: number;
  name: string;
  max_input_channels: number;
  default_samplerate: number;
  is_default_input: boolean;
}

export interface AudioDevicesResult {
  devices: AudioDeviceInfo[];
  current_input_device: string | number;
  current_sample_rate: number;
}

export interface ModelValidationIssue {
  code: string;
  field: string;
  message: string;
}

export interface ModelValidationResult {
  valid: boolean;
  normalized: {
    backend?: string;
    name?: string;
    device?: string;
    compute_type?: string;
  };
  errors: ModelValidationIssue[];
  warnings: ModelValidationIssue[];
}

export interface StorageStatusResult {
  storage_root: string;
  effective_paths: Record<string, string>;
  sizes: {
    models_bytes: number;
    history_bytes: number;
    exports_bytes: number;
    runtime_bytes: number;
    total_bytes: number;
  };
  disk_free_bytes: number;
  migration_estimate: {
    bytes_required: number;
    disk_free_bytes: number;
    breakdown: Record<string, number>;
  };
  active_target: string | null;
}

export interface HistoryEntry {
  id: number;
  created_at: string;
  text: string;
  duration_ms: number | null;
  backend: string;
  model: string;
  status: string;
}

export interface ServerEventBase {
  protocol_version: string;
  timestamp: string;
}

export type ServerEvent =
  | (ServerEventBase & { type: "state"; state: "idle" | "recording" | "processing" })
  | (ServerEventBase & { type: "transcription"; text: string; duration_ms: number | null; entry: HistoryEntry | null })
  | (ServerEventBase & { type: "history_appended"; entry: HistoryEntry })
  | (ServerEventBase & { type: "model_download"; download_id?: string; status: "starting" | "resolving" | "downloading" | "finalizing" | "completed" | "failed"; backend: string; name: string; message: string; progress_pct?: number; bytes_total?: number | null; bytes_completed?: number | null; bytes_remaining?: number | null; repo_id?: string })
  | (ServerEventBase & { type: "model_download_progress"; download_id: string; status: "starting" | "resolving" | "downloading" | "finalizing" | "completed" | "failed"; backend: string; name: string; message: string; progress_pct: number; bytes_total?: number | null; bytes_completed?: number | null; bytes_remaining?: number | null; repo_id?: string })
  | (ServerEventBase & { type: "storage_migration"; status: "starting" | "copying" | "verifying" | "cleanup" | "completed" | "failed"; target_root: string; message: string; progress_pct: number; total_bytes?: number | null; copied_bytes?: number | null })
  | (ServerEventBase & { type: "storage_updated"; storage_root: string; persisted: boolean })
  | (ServerEventBase & { type: "error"; message: string })
  | (ServerEventBase & { type: "dictionary_updated"; key: string; value: string })
  | (ServerEventBase & { type: "dictionary_deleted"; key: string })
  | (ServerEventBase & { type: "shutting_down" });

export type IncomingMessage = ProtocolResponse | ServerEvent;

export function isProtocolResponse(message: unknown): message is ProtocolResponse {
  return (
    typeof message === "object" &&
    message !== null &&
    (message as { type?: string }).type === "response"
  );
}
