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