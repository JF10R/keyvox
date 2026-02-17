import type { IncomingMessage, ProtocolResponse } from "./protocol";
import { isProtocolResponse } from "./protocol";

type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

type PendingRequest = {
  resolve: (response: ProtocolResponse) => void;
  reject: (error: Error) => void;
  timeoutId: ReturnType<typeof setTimeout>;
};

export class KeyvoxWsClient {
  private ws: WebSocket | null = null;
  private requestCounter = 0;
  private pending = new Map<string, PendingRequest>();

  onMessage: ((message: IncomingMessage) => void) | null = null;
  onStatus: ((status: ConnectionStatus, detail?: string) => void) | null = null;

  private emitStatus(status: ConnectionStatus, detail?: string): void {
    this.onStatus?.(status, detail);
  }

  async connect(portCandidates: number[]): Promise<number> {
    this.disconnect();
    this.emitStatus("connecting");

    for (const port of portCandidates) {
      const connected = await this.tryOpen(port);
      if (connected) {
        this.emitStatus("connected");
        return port;
      }
    }

    this.emitStatus("error", "Unable to connect to Keyvox backend");
    throw new Error("Unable to connect to Keyvox backend");
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      this.ws.close();
      this.ws = null;
    }

    for (const pending of this.pending.values()) {
      clearTimeout(pending.timeoutId);
      pending.reject(new Error("Socket disconnected"));
    }
    this.pending.clear();
    this.emitStatus("disconnected");
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  async sendCommand(
    type: string,
    payload: Record<string, unknown> = {},
    timeoutMs = 7000,
  ): Promise<ProtocolResponse> {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error("Socket is not connected");
    }

    const requestId = `req-${++this.requestCounter}`;
    const frame = {
      type,
      request_id: requestId,
      ...payload,
    };

    return new Promise<ProtocolResponse>((resolve, reject) => {
      const timeoutId = setTimeout(() => {
        this.pending.delete(requestId);
        reject(new Error(`Request timed out: ${type}`));
      }, timeoutMs);

      this.pending.set(requestId, { resolve, reject, timeoutId });
      this.ws!.send(JSON.stringify(frame));
    });
  }

  private async tryOpen(port: number): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      const socket = new WebSocket(`ws://localhost:${port}`);
      let settled = false;

      const fail = () => {
        if (settled) {
          return;
        }
        settled = true;
        socket.close();
        resolve(false);
      };

      const timer = setTimeout(fail, 1000);

      socket.onopen = () => {
        if (settled) {
          return;
        }
        settled = true;
        clearTimeout(timer);
        this.ws = socket;

        socket.onmessage = (event) => this.handleMessage(event.data);
        socket.onclose = () => {
          this.ws = null;
          this.emitStatus("disconnected");
        };
        socket.onerror = () => {
          this.emitStatus("error", "Socket error");
        };

        resolve(true);
      };

      socket.onerror = fail;
      socket.onclose = fail;
    });
  }

  private handleMessage(raw: string): void {
    let parsed: IncomingMessage;
    try {
      parsed = JSON.parse(raw) as IncomingMessage;
    } catch {
      this.emitStatus("error", "Received invalid JSON message");
      return;
    }

    if (isProtocolResponse(parsed) && parsed.request_id) {
      const requestKey = String(parsed.request_id);
      const pending = this.pending.get(requestKey);
      if (pending) {
        clearTimeout(pending.timeoutId);
        this.pending.delete(requestKey);
        if (parsed.ok) {
          pending.resolve(parsed);
        } else {
          const message = parsed.error?.message ?? "Unknown protocol error";
          pending.reject(new Error(message));
        }
      }
    }

    this.onMessage?.(parsed);
  }
}