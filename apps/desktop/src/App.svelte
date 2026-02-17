<script lang="ts">
  import { onDestroy, onMount } from "svelte";

  import { backendPreflight, backendStatus, startBackend, stopBackend } from "./lib/backend";
  import type {
    HistoryEntry,
    IncomingMessage,
    ProtocolResponse,
    ServerEvent,
  } from "./lib/protocol";
  import { isProtocolResponse } from "./lib/protocol";
  import { KeyvoxWsClient } from "./lib/websocket";

  const DEFAULT_PORT = 9876;
  const PORT_WINDOW = 10;
  const MAX_RECONNECT_ATTEMPTS = 5;
  const BASE_RECONNECT_DELAY_MS = 1200;
  const MAX_RECONNECT_DELAY_MS = 9000;

  type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";
  type NoticeLevel = "info" | "success" | "error";
  type RuntimeIssue = "none" | "backend_unavailable" | "transport_error";

  type Notice = {
    id: number;
    level: NoticeLevel;
    text: string;
  };

  const client = new KeyvoxWsClient();

  let notices: Notice[] = [];
  let noticeCounter = 0;

  let connectionStatus: ConnectionStatus = "disconnected";
  let connectionDetail = "";
  let backendRunning = false;
  let backendManaged = false;
  let booting = false;
  let preferredPort = DEFAULT_PORT;
  let boundPort: number | null = null;
  let backendCommand = "";

  let engineState: "idle" | "recording" | "processing" = "idle";
  let protocolVersion = "";
  let lastTranscript = "";
  let lastError = "";

  let historyEntries: HistoryEntry[] = [];
  let historySearch = "";
  let historyLimit = 100;
  let exportFormat: "txt" | "csv" = "txt";

  let hotkeyInput = "ctrl_r";
  let modelBackend = "auto";
  let modelName = "large-v3-turbo";
  let modelDevice = "cuda";
  let modelComputeType = "float16";
  let audioDevice: string | number = "default";
  let audioSampleRate = 16000;
  let textInsertionEnabled = true;

  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempts = 0;
  let reconnectInFlight = false;
  let reconnectPaused = false;
  let runtimeIssue: RuntimeIssue = "none";
  let runtimeBlockingMessage = "";

  client.onStatus = (status, detail) => {
    connectionStatus = status;
    connectionDetail = detail ?? "";
    if (status === "connected") {
      resetReconnectState();
      runtimeIssue = "none";
      runtimeBlockingMessage = "";
    }
    if (status === "error") {
      runtimeIssue = "transport_error";
    }
    if (status === "disconnected" && backendRunning) {
      runtimeIssue = "backend_unavailable";
      scheduleReconnect();
      return;
    }
    if (status === "disconnected" && !backendRunning) {
      runtimeIssue = "none";
    }
  };

  client.onMessage = (message: IncomingMessage) => {
    if (isProtocolResponse(message)) {
      consumeResponse(message);
      return;
    }
    consumeEvent(message as ServerEvent);
  };

  function notify(level: NoticeLevel, text: string): void {
    const id = ++noticeCounter;
    notices = [...notices, { id, level, text }];
    setTimeout(() => {
      notices = notices.filter((notice) => notice.id !== id);
    }, 3500);
  }

  function consumeResponse(response: ProtocolResponse): void {
    protocolVersion = response.protocol_version;
    if (!response.ok) {
      const message = response.error?.message ?? "Unknown protocol error";
      notify("error", message);
      return;
    }

    if (response.response_type === "server_info") {
      const port = response.result?.port;
      if (typeof port === "number") {
        boundPort = port;
        connectionDetail = `ws://localhost:${port}`;
      }
    }
  }

  function consumeEvent(event: ServerEvent): void {
    protocolVersion = event.protocol_version;
    if (event.type === "state") {
      engineState = event.state;
      return;
    }
    if (event.type === "transcription") {
      lastTranscript = event.text;
      if (event.entry) {
        historyEntries = [event.entry, ...historyEntries].slice(0, historyLimit);
      }
      return;
    }
    if (event.type === "history_appended") {
      historyEntries = [event.entry, ...historyEntries].slice(0, historyLimit);
      return;
    }
    if (event.type === "error") {
      lastError = event.message;
      notify("error", event.message);
      return;
    }
    if (event.type === "shutting_down") {
      notify("info", "Backend is shutting down");
      return;
    }
  }

  function orderedPorts(seed: number): number[] {
    const baseRange = Array.from({ length: PORT_WINDOW }, (_, index) => DEFAULT_PORT + index);
    if (baseRange.includes(seed)) {
      return [seed, ...baseRange.filter((port) => port !== seed)];
    }
    return [seed, ...baseRange];
  }

  async function connectToBackend(seedPort: number): Promise<number> {
    const activePort = await client.connect(orderedPorts(seedPort));
    boundPort = activePort;
    backendRunning = true;
    connectionDetail = `ws://localhost:${activePort}`;
    await hydrateFromServer();
    return activePort;
  }

  async function hydrateFromServer(): Promise<void> {
    await sendCommand("ping");
    await sendCommand("server_info");
    await refreshConfig();
    await refreshHistory();
  }

  function clearReconnectTimer(): void {
    if (!reconnectTimer) {
      return;
    }
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  function resetReconnectState(): void {
    reconnectAttempts = 0;
    reconnectPaused = false;
    reconnectInFlight = false;
    clearReconnectTimer();
  }

  function scheduleReconnect(): void {
    if (reconnectTimer || reconnectInFlight || !backendRunning) {
      return;
    }
    if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      if (!reconnectPaused) {
        reconnectPaused = true;
        notify("error", `Auto-reconnect paused after ${MAX_RECONNECT_ATTEMPTS} failed attempts.`);
      }
      connectionDetail = "Auto-reconnect paused. Click Reconnect to retry.";
      return;
    }

    const delayMs = Math.min(
      BASE_RECONNECT_DELAY_MS * 2 ** reconnectAttempts,
      MAX_RECONNECT_DELAY_MS,
    );
    reconnectTimer = setTimeout(() => {
      void attemptReconnect();
    }, delayMs);
  }

  async function attemptReconnect(): Promise<void> {
    clearReconnectTimer();
    if (!backendRunning || client.isConnected() || reconnectInFlight) {
      return;
    }

    reconnectInFlight = true;
    const hadRetries = reconnectAttempts > 0;

    try {
      await connectToBackend(boundPort ?? preferredPort);
      if (hadRetries) {
        notify("success", "Reconnected to backend.");
      }
    } catch (error) {
      reconnectAttempts += 1;
      runtimeIssue = "backend_unavailable";
      connectionStatus = "error";
      connectionDetail =
        `Reconnect ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS} failed: ${String(error)}`;
      scheduleReconnect();
    } finally {
      reconnectInFlight = false;
    }
  }

  function formatRuntimeIssue(issue: RuntimeIssue): string {
    if (issue === "backend_unavailable") {
      return "backend unavailable";
    }
    if (issue === "transport_error") {
      return "transport error";
    }
    return "-";
  }

  function autoReconnectLabel(): string {
    if (reconnectPaused) {
      return "paused";
    }
    if (reconnectInFlight) {
      return "retrying";
    }
    if (reconnectAttempts > 0) {
      return `${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}`;
    }
    return "ready";
  }

  async function runBackendPreflight(seedPort: number): Promise<void> {
    const report = await backendPreflight(seedPort, backendCommand.trim() || undefined);
    if (!report.ok) {
      runtimeBlockingMessage = report.message;
      runtimeIssue = "backend_unavailable";
      throw new Error(report.message);
    }
    runtimeBlockingMessage = "";
  }

  async function connectExistingBackend(seedPort: number): Promise<number | null> {
    try {
      const port = await connectToBackend(seedPort);
      backendManaged = false;
      return port;
    } catch {
      return null;
    }
  }

  async function startManagedBackend(seedPort: number): Promise<number> {
    await runBackendPreflight(seedPort);
    const status = await startBackend(seedPort, backendCommand.trim() || undefined);
    backendRunning = status.running;
    backendManaged = status.managed;
    boundPort = status.port;
    const port = await connectToBackend(status.port ?? seedPort);
    backendManaged = status.managed;
    return port;
  }

  async function sendCommand(
    type: string,
    payload: Record<string, unknown> = {},
  ): Promise<ProtocolResponse> {
    return client.sendCommand(type, payload);
  }

  async function refreshConfig(): Promise<void> {
    const response = await sendCommand("get_full_config");
    const config = response.result?.config as Record<string, unknown> | undefined;
    if (!config) {
      return;
    }

    const model = (config.model as Record<string, unknown> | undefined) ?? {};
    const audio = (config.audio as Record<string, unknown> | undefined) ?? {};
    const hotkey = (config.hotkey as Record<string, unknown> | undefined) ?? {};
    const textInsertion =
      (config.text_insertion as Record<string, unknown> | undefined) ?? {};

    hotkeyInput = String(hotkey.push_to_talk ?? hotkeyInput);
    modelBackend = String(model.backend ?? modelBackend);
    modelName = String(model.name ?? modelName);
    modelDevice = String(model.device ?? modelDevice);
    modelComputeType = String(model.compute_type ?? modelComputeType);
    audioDevice = (audio.input_device as string | number | undefined) ?? audioDevice;
    audioSampleRate = Number(audio.sample_rate ?? audioSampleRate);
    textInsertionEnabled = Boolean(textInsertion.enabled ?? textInsertionEnabled);
  }

  async function refreshHistory(): Promise<void> {
    const response = await sendCommand("get_history", {
      limit: historyLimit,
      offset: 0,
      search: historySearch,
    });
    const entries = response.result?.entries;
    if (Array.isArray(entries)) {
      historyEntries = entries as HistoryEntry[];
    }
  }

  async function handleStartBackend(): Promise<void> {
    resetReconnectState();
    try {
      if (client.isConnected()) {
        notify("info", "Already connected to backend.");
        return;
      }
      const connectedPort = await connectExistingBackend(boundPort ?? preferredPort);
      if (connectedPort !== null) {
        runtimeIssue = "none";
        runtimeBlockingMessage = "";
        notify("success", `Connected to existing backend on port ${connectedPort}`);
        return;
      }

      const port = await startManagedBackend(preferredPort);
      runtimeIssue = "none";
      notify("success", `Started and connected to managed backend on port ${port}`);
    } catch (error) {
      runtimeIssue = "backend_unavailable";
      backendRunning = false;
      notify("error", `Failed to start backend: ${String(error)}`);
    }
  }

  async function handleReconnect(): Promise<void> {
    resetReconnectState();
    try {
      const port = await connectToBackend(boundPort ?? preferredPort);
      runtimeIssue = "none";
      notify("success", `Connected on port ${port}`);
    } catch (error) {
      runtimeIssue = "backend_unavailable";
      notify("error", `Reconnect failed: ${String(error)}`);
      if (backendRunning) {
        scheduleReconnect();
      }
    }
  }

  async function handleStopBackend(): Promise<void> {
    try {
      if (!backendManaged) {
        notify("info", "Connected backend is unmanaged. It will not be stopped from this app.");
        return;
      }

      resetReconnectState();
      backendRunning = false;
      if (client.isConnected()) {
        await sendCommand("shutdown");
      }
      const status = await stopBackend();
      backendRunning = status.running;
      backendManaged = status.managed;
      boundPort = status.port;
      runtimeIssue = "none";
      client.disconnect();
      notify("info", "Managed backend stopped");
    } catch (error) {
      notify("error", `Failed to stop backend: ${String(error)}`);
    }
  }

  async function saveHotkey(): Promise<void> {
    await sendCommand("set_hotkey", { hotkey: hotkeyInput });
    notify("success", "Hotkey updated. Restart backend to apply.");
  }

  async function saveModel(): Promise<void> {
    await sendCommand("set_model", {
      backend: modelBackend,
      name: modelName,
      device: modelDevice,
      compute_type: modelComputeType,
    });
    notify("success", "Model config saved. Restart backend to apply.");
  }

  async function saveAudio(): Promise<void> {
    await sendCommand("set_audio_device", {
      input_device: audioDevice,
      sample_rate: Number(audioSampleRate),
    });
    notify("success", "Audio config saved. Restart backend to apply.");
  }

  async function saveTextInsertion(): Promise<void> {
    await sendCommand("set_config_section", {
      section: "text_insertion",
      values: { enabled: textInsertionEnabled },
    });
    notify("success", "Text insertion setting updated.");
  }

  async function deleteHistoryItem(id: number): Promise<void> {
    await sendCommand("delete_history_item", { id });
    historyEntries = historyEntries.filter((entry) => entry.id !== id);
    notify("success", `Deleted history entry #${id}`);
  }

  async function clearHistory(): Promise<void> {
    await sendCommand("clear_history");
    historyEntries = [];
    notify("success", "History cleared");
  }

  async function exportHistory(): Promise<void> {
    const response = await sendCommand("export_history", { format: exportFormat });
    const output = response.result?.path;
    notify("success", `Exported history to ${String(output ?? "unknown path")}`);
  }

  async function copyTranscript(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      notify("success", "Transcript copied to clipboard");
    } catch {
      notify("error", "Clipboard write failed");
    }
  }

  async function stopManagedBackendOnExit(): Promise<void> {
    if (!backendManaged) {
      return;
    }
    try {
      resetReconnectState();
      backendRunning = false;
      await stopBackend();
    } catch {
      // Best-effort cleanup on app shutdown.
    }
  }

  onMount(async () => {
    booting = true;
    resetReconnectState();
    try {
      const localStatus = await backendStatus();
      backendManaged = localStatus.managed;
      boundPort = localStatus.port;
      const connectedPort = await connectExistingBackend(boundPort ?? preferredPort);
      if (connectedPort !== null) {
        runtimeIssue = "none";
        notify("success", `Connected to existing backend on port ${connectedPort}`);
        return;
      }

      const port = await startManagedBackend(preferredPort);
      runtimeIssue = "none";
      notify("success", `Started and connected to managed backend on port ${port}`);
    } catch (error) {
      runtimeIssue = "backend_unavailable";
      notify("error", `Desktop startup failed: ${String(error)}`);
    } finally {
      booting = false;
    }
  });

  onDestroy(() => {
    resetReconnectState();
    void stopManagedBackendOnExit();
    client.disconnect();
  });
</script>

<div class="app-shell">
  <header class="hero">
    <div>
      <p class="eyebrow">Keyvox Desktop</p>
      <h1>Professional Voice Workflow Console</h1>
      <p class="subtitle">Live engine status, modern controls, and full transcription operations in one workspace.</p>
    </div>
    <div class="status-pill {connectionStatus}">
      <span>{connectionStatus}</span>
      {#if boundPort}
        <small>:{boundPort}</small>
      {/if}
    </div>
  </header>
  {#if runtimeBlockingMessage}
    <div class="runtime-banner">
      {runtimeBlockingMessage}
    </div>
  {/if}

  <main class="grid">
    <section class="panel connection">
      <h2>Engine Control</h2>
      <div class="row">
        <label for="preferred-port">Preferred Port</label>
        <input
          id="preferred-port"
          type="number"
          bind:value={preferredPort}
          min="1024"
          max="65535"
        />
      </div>
      <div class="row">
        <label for="backend-command">Backend Command</label>
        <input
          id="backend-command"
          type="text"
          bind:value={backendCommand}
          placeholder="keyvox"
        />
      </div>
      <div class="button-row">
        <button on:click={handleStartBackend} disabled={booting}>Start Backend</button>
        <button class="ghost" on:click={handleStopBackend} disabled={!backendManaged}>Stop Managed Backend</button>
        <button class="ghost" on:click={handleReconnect} disabled={booting || reconnectInFlight}>Reconnect</button>
      </div>
      <dl class="kv">
        <div>
          <dt>Backend Running</dt>
          <dd>{backendRunning ? "yes" : "no"}</dd>
        </div>
        <div>
          <dt>Engine State</dt>
          <dd>{engineState}</dd>
        </div>
        <div>
          <dt>Protocol</dt>
          <dd>{protocolVersion || "-"}</dd>
        </div>
        <div>
          <dt>Socket</dt>
          <dd>{connectionDetail || "n/a"}</dd>
        </div>
        <div>
          <dt>Owned by Desktop</dt>
          <dd>{backendManaged ? "yes" : "no"}</dd>
        </div>
        <div>
          <dt>Runtime Issue</dt>
          <dd>{formatRuntimeIssue(runtimeIssue)}</dd>
        </div>
        <div>
          <dt>Auto-Reconnect</dt>
          <dd>{autoReconnectLabel()}</dd>
        </div>
      </dl>
      {#if lastError}
        <p class="error-inline">Last error: {lastError}</p>
      {/if}
    </section>

    <section class="panel transcript">
      <h2>Latest Transcription</h2>
      <div class="transcript-box">
        {#if lastTranscript}
          <p>{lastTranscript}</p>
        {:else}
          <p class="muted">No transcription received yet.</p>
        {/if}
      </div>
      <div class="button-row">
        <button class="ghost" on:click={() => copyTranscript(lastTranscript)} disabled={!lastTranscript}>Copy</button>
        <button class="ghost" on:click={refreshHistory}>Refresh History</button>
      </div>
    </section>

    <section class="panel settings">
      <h2>Settings</h2>
      <div class="settings-grid">
        <div class="field-group">
          <h3>Hotkey</h3>
          <input type="text" bind:value={hotkeyInput} />
          <button class="ghost" on:click={saveHotkey}>Save Hotkey</button>
        </div>

        <div class="field-group">
          <h3>Model</h3>
          <input type="text" bind:value={modelBackend} placeholder="backend" />
          <input type="text" bind:value={modelName} placeholder="model name" />
          <input type="text" bind:value={modelDevice} placeholder="device" />
          <input type="text" bind:value={modelComputeType} placeholder="compute_type" />
          <button class="ghost" on:click={saveModel}>Save Model</button>
        </div>

        <div class="field-group">
          <h3>Audio</h3>
          <input type="text" bind:value={audioDevice} placeholder="input device" />
          <input type="number" bind:value={audioSampleRate} min="8000" max="96000" />
          <button class="ghost" on:click={saveAudio}>Save Audio</button>
        </div>

        <div class="field-group">
          <h3>Text Insertion</h3>
          <label class="checkbox">
            <input type="checkbox" bind:checked={textInsertionEnabled} />
            Enabled
          </label>
          <button class="ghost" on:click={saveTextInsertion}>Save Text Insertion</button>
        </div>
      </div>
    </section>

    <section class="panel history">
      <div class="history-head">
        <h2>History</h2>
        <div class="button-row compact">
          <button class="ghost" on:click={clearHistory}>Clear</button>
          <select bind:value={exportFormat}>
            <option value="txt">TXT</option>
            <option value="csv">CSV</option>
          </select>
          <button class="ghost" on:click={exportHistory}>Export</button>
        </div>
      </div>

      <div class="history-search">
        <input
          type="text"
          bind:value={historySearch}
          placeholder="Search transcript text"
        />
        <button class="ghost" on:click={refreshHistory}>Search</button>
      </div>

      <ul class="history-list">
        {#if historyEntries.length === 0}
          <li class="muted">No history entries yet.</li>
        {:else}
          {#each historyEntries as entry (entry.id)}
            <li>
              <div class="history-meta">
                <strong>#{entry.id}</strong>
                <span>{entry.created_at}</span>
                <span>{entry.backend}</span>
                <span>{entry.model}</span>
              </div>
              <p>{entry.text}</p>
              <div class="button-row compact">
                <button class="ghost" on:click={() => copyTranscript(entry.text)}>Copy</button>
                <button class="ghost" on:click={() => deleteHistoryItem(entry.id)}>Delete</button>
              </div>
            </li>
          {/each}
        {/if}
      </ul>
    </section>
  </main>

  <aside class="notices">
    {#each notices as notice (notice.id)}
      <div class="notice {notice.level}">{notice.text}</div>
    {/each}
  </aside>
</div>
