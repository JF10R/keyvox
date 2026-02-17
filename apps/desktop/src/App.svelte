<script lang="ts">
  import { onDestroy, onMount } from "svelte";

  import {
    backendPreflight,
    backendStatus,
    pickStorageFolder,
    setTrayStatus,
    startBackend,
    stopBackend,
  } from "./lib/backend";
  import type {
    CapabilitiesResult,
    HistoryEntry,
    IncomingMessage,
    ModelRequirement,
    ProtocolResponse,
    ServerEvent,
    StorageStatusResult,
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
  let capabilities: CapabilitiesResult | null = null;
  let modelDownloadState: "idle" | "loading" | "completed" | "error" = "idle";
  let modelDownloadMessage = "";
  let modelDownloadLookup: Record<string, boolean | null> = {};
  let modelRequirementLookup: Record<string, ModelRequirement> = {};
  let selectedModelRequirement: ModelRequirement | null = null;
  let modelDownloadProgressPct = 0;
  let modelDownloadBytesTotal: number | null = null;
  let modelDownloadBytesDone: number | null = null;
  let modelDownloadBytesRemaining: number | null = null;

  let storageStatus: StorageStatusResult | null = null;
  let storageRootInput = "";
  let storageMigrationState: "idle" | "running" | "completed" | "error" = "idle";
  let storageMigrationMessage = "";
  let storageMigrationProgressPct = 0;

  let dictionaryEntries: Record<string, string> = {};
  let dictNewKey = "";
  let dictNewValue = "";
  let dictEditingKey: string | null = null;
  let dictEditingValue = "";
  let validationErrors: Record<string, string> = {};

  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempts = 0;
  let reconnectInFlight = false;
  let reconnectPaused = false;
  let runtimeIssue: RuntimeIssue = "none";
  let runtimeBlockingMessage = "";
  let isDarkTheme = false;

  function toggleTheme(): void {
    isDarkTheme = !isDarkTheme;
    const theme = isDarkTheme ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("keyvox-theme", theme);
  }

  function dismissNotice(id: number): void {
    notices = notices.filter((n) => n.id !== id);
  }

  const STATUS_UNKNOWN = "unknown";
  const STATUS_MISSING = "missing";
  const STATUS_READY = "ready";
  let modelStatusValue: boolean | null | undefined = undefined;
  let modelCacheStatus = STATUS_UNKNOWN;
  let trayStatusText = "Keyvox Desktop - ready";

  $: modelStatusValue = modelDownloadLookup[`${modelBackend}::${modelName}`];
  $: modelCacheStatus =
    modelStatusValue === true ? STATUS_READY : modelStatusValue === false ? STATUS_MISSING : STATUS_UNKNOWN;
  $: selectedModelRequirement = modelRequirementLookup[`${modelBackend}::${modelName}`] ?? null;
  $: {
    if (capabilities?.compute_types?.[modelBackend]) {
      const validComputeTypes = capabilities.compute_types[modelBackend];
      if (!validComputeTypes.includes(modelComputeType)) {
        modelComputeType = validComputeTypes[0] || "float16";
      }
    }
  }
  $: trayStatusText =
    modelDownloadState === "loading"
      ? `Keyvox Desktop - loading model ${modelDownloadProgressPct}%`
      : "Keyvox Desktop - ready";
  $: if (typeof document !== "undefined") {
    document.title = trayStatusText;
  }
  $: if (typeof window !== "undefined") {
    void setTrayStatus(trayStatusText).catch(() => undefined);
  }

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
    if (event.type === "model_download_progress" || event.type === "model_download") {
      modelDownloadMessage = `${event.backend}:${event.name} - ${event.message}`;
      if (typeof event.progress_pct === "number") {
        modelDownloadProgressPct = Math.max(0, Math.min(100, event.progress_pct));
      }
      modelDownloadBytesTotal = typeof event.bytes_total === "number" ? event.bytes_total : null;
      modelDownloadBytesDone = typeof event.bytes_completed === "number" ? event.bytes_completed : null;
      modelDownloadBytesRemaining = typeof event.bytes_remaining === "number" ? event.bytes_remaining : null;
      if (
        event.status === "starting"
        || event.status === "resolving"
        || event.status === "downloading"
        || event.status === "finalizing"
      ) {
        modelDownloadState = "loading";
        return;
      }
      if (event.status === "completed") {
        modelDownloadState = "completed";
        notify("success", modelDownloadMessage);
        void refreshCapabilities();
        return;
      }
      modelDownloadState = "error";
      notify("error", modelDownloadMessage);
      return;
    }
    if (event.type === "storage_migration") {
      storageMigrationMessage = event.message;
      storageMigrationProgressPct = event.progress_pct;
      if (
        event.status === "starting"
        || event.status === "copying"
        || event.status === "verifying"
        || event.status === "cleanup"
      ) {
        storageMigrationState = "running";
        return;
      }
      if (event.status === "completed") {
        storageMigrationState = "completed";
        storageRootInput = event.target_root;
        notify("success", "Storage migration completed");
        void refreshStorageStatus();
        void refreshCapabilities();
        return;
      }
      storageMigrationState = "error";
      notify("error", event.message);
      return;
    }
    if (event.type === "storage_updated") {
      void refreshStorageStatus();
      return;
    }
    if (event.type === "dictionary_updated") {
      dictionaryEntries[event.key] = event.value;
      dictionaryEntries = dictionaryEntries;
      return;
    }
    if (event.type === "dictionary_deleted") {
      delete dictionaryEntries[event.key];
      dictionaryEntries = dictionaryEntries;
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
    await refreshCapabilities();
    await refreshStorageStatus();
    await refreshHistory();
    await refreshDictionary();
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

  function formatBytes(value: number | null | undefined): string {
    if (typeof value !== "number" || Number.isNaN(value) || value < 0) {
      return "-";
    }
    const units = ["B", "KB", "MB", "GB", "TB"];
    let size = value;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
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
    const paths = (config.paths as Record<string, unknown> | undefined) ?? {};
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
    storageRootInput = String(paths.storage_root ?? storageRootInput);
  }

  async function refreshCapabilities(): Promise<void> {
    const response = await sendCommand("get_capabilities");
    const result = response.result as CapabilitiesResult | undefined;
    if (!result) {
      return;
    }
    capabilities = result;

    const lookup: Record<string, boolean | null> = {};
    for (const item of result.model_download_status ?? []) {
      lookup[`${item.backend}::${item.name}`] = item.downloaded;
    }
    modelDownloadLookup = lookup;

    const requirementLookup: Record<string, ModelRequirement> = {};
    for (const req of result.model_requirements ?? []) {
      requirementLookup[`${req.backend}::${req.name}`] = req;
    }
    modelRequirementLookup = requirementLookup;
    if (result.storage?.storage_root) {
      storageRootInput = result.storage.storage_root;
    }

    if (result.active_model_download) {
      modelDownloadState = "loading";
      modelDownloadMessage =
        `${result.active_model_download.backend}:${result.active_model_download.name} - download in progress`;
    } else if (modelDownloadState === "loading") {
      modelDownloadState = "idle";
    }
  }

  async function refreshStorageStatus(): Promise<void> {
    const response = await sendCommand("get_storage_status");
    const result = response.result as StorageStatusResult | undefined;
    if (!result) {
      return;
    }
    storageStatus = result;
    if (result.storage_root) {
      storageRootInput = result.storage_root;
    }
    if (result.active_target) {
      storageMigrationState = "running";
    }
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

  async function refreshDictionary(): Promise<void> {
    const response = await sendCommand("get_dictionary");
    const entries = response.result?.entries as Record<string, string> | undefined;
    if (entries) {
      dictionaryEntries = entries;
    }
  }

  async function addDictionaryEntry(): Promise<void> {
    const key = dictNewKey.trim();
    const value = dictNewValue.trim();
    if (!key || !value) {
      notify("error", "Both pattern and replacement are required.");
      return;
    }
    const isUpdate = key in dictionaryEntries;
    await sendCommand("set_dictionary", { key, value });
    dictionaryEntries[key] = value;
    dictionaryEntries = dictionaryEntries;
    dictNewKey = "";
    dictNewValue = "";
    notify("success", isUpdate ? "Updated existing entry" : "Dictionary entry added");
  }

  async function updateDictionaryEntry(key: string, value: string): Promise<void> {
    const trimmedValue = value.trim();
    if (!trimmedValue) {
      notify("error", "Replacement cannot be empty.");
      return;
    }
    await sendCommand("set_dictionary", { key, value: trimmedValue });
    dictionaryEntries[key] = trimmedValue;
    dictionaryEntries = dictionaryEntries;
    dictEditingKey = null;
    dictEditingValue = "";
    notify("success", "Dictionary entry updated");
  }

  async function deleteDictionaryEntry(key: string): Promise<void> {
    if (!confirm(`Delete dictionary entry "${key}"?`)) {
      return;
    }
    await sendCommand("delete_dictionary", { key });
    delete dictionaryEntries[key];
    dictionaryEntries = dictionaryEntries;
    notify("success", "Dictionary entry deleted");
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
    const validation = await sendCommand("validate_model_config", {
      backend: modelBackend,
      name: modelName,
      device: modelDevice,
      compute_type: modelComputeType,
    });
    const validationResult = validation.result as Record<string, unknown> | undefined;
    if (!validationResult || validationResult["valid"] !== true) {
      validationErrors = {};
      const errors = (validationResult?.errors as Array<{ field: string; message: string }>) ?? [];
      const warnings = (validationResult?.warnings as Array<{ field: string; message: string }>) ?? [];
      for (const err of errors) {
        validationErrors[err.field] = err.message;
      }
      for (const warn of warnings) {
        if (!validationErrors[warn.field]) {
          validationErrors[warn.field] = warn.message;
        }
      }
      validationErrors = validationErrors;
      notify("error", "Model config is invalid. Fix fields before saving.");
      return;
    }

    validationErrors = {};
    await sendCommand("set_model", {
      backend: modelBackend,
      name: modelName,
      device: modelDevice,
      compute_type: modelComputeType,
    });
    notify("success", "Model config saved. Restart backend to apply.");
    await refreshCapabilities();
  }

  async function downloadSelectedModel(): Promise<void> {
    if (selectedModelRequirement && selectedModelRequirement.enough_space === false) {
      notify(
        "error",
        `Not enough free space for model download (${formatBytes(selectedModelRequirement.remaining_bytes)} needed).`,
      );
      return;
    }
    modelDownloadState = "loading";
    modelDownloadProgressPct = 0;
    modelDownloadBytesTotal = selectedModelRequirement?.estimated_total_bytes ?? null;
    modelDownloadBytesDone = selectedModelRequirement?.already_present_bytes ?? null;
    modelDownloadBytesRemaining = selectedModelRequirement?.remaining_bytes ?? null;
    modelDownloadMessage = `${modelBackend}:${modelName} - queued`;
    try {
      const response = await sendCommand("download_model", {
        backend: modelBackend,
        name: modelName,
      });
      const result = response.result as Record<string, unknown> | undefined;
      if (result?.already_downloaded === true) {
        modelDownloadState = "completed";
        modelDownloadMessage = `${modelBackend}:${modelName} - already downloaded`;
        notify("success", "Model already downloaded locally.");
        await refreshCapabilities();
        return;
      }
      notify("info", "Model download started in background.");
    } catch (error) {
      modelDownloadState = "error";
      modelDownloadMessage = `${modelBackend}:${modelName} - download failed`;
      notify("error", `Failed to queue model download: ${String(error)}`);
    }
  }

  async function browseStorageRoot(): Promise<void> {
    const selected = await pickStorageFolder();
    if (selected) {
      storageRootInput = selected;
    }
  }

  async function applyStorageRoot(): Promise<void> {
    const nextRoot = storageRootInput.trim();
    if (!nextRoot) {
      notify("error", "Storage root cannot be empty.");
      return;
    }
    storageMigrationState = "running";
    storageMigrationProgressPct = 0;
    storageMigrationMessage = "Preparing migration";
    try {
      await sendCommand("set_storage_root", { storage_root: nextRoot });
      notify("info", "Storage migration started.");
    } catch (error) {
      storageMigrationState = "error";
      storageMigrationMessage = String(error);
      notify("error", `Storage migration failed to start: ${String(error)}`);
    }
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
    // Theme init — saved preference first, then OS preference
    const savedTheme = localStorage.getItem("keyvox-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    isDarkTheme = savedTheme ? savedTheme === "dark" : prefersDark;
    document.documentElement.setAttribute("data-theme", isDarkTheme ? "dark" : "light");

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

<a href="#main-content" class="skip-link">Skip to content</a>
<div class="app-shell">
  <header class="hero">
    <div>
      <p class="eyebrow">Keyvox Desktop</p>
      <h1>Professional Voice Workflow Console</h1>
      <p class="subtitle">Live engine status, modern controls, and full transcription operations in one workspace.</p>
    </div>
    <div class="hero-controls">
      <button
        type="button"
        class="theme-toggle"
        on:click={toggleTheme}
        aria-label={isDarkTheme ? "Switch to light theme" : "Switch to dark theme"}
      >{isDarkTheme ? "☀" : "☾"}</button>
      <div
        class="status-pill {connectionStatus} {modelDownloadState === 'loading' || storageMigrationState === 'running' ? 'loading' : ''}"
        role="status"
        aria-label="Connection: {connectionStatus}{boundPort ? ', port ' + boundPort : ''}"
      >
        <span aria-hidden="true">{connectionStatus}</span>
        {#if boundPort}
          <small aria-hidden="true">:{boundPort}</small>
        {/if}
        {#if modelDownloadState === "loading"}
          <span class="loading-dot" aria-hidden="true"></span>
          <small>model loading</small>
        {:else if storageMigrationState === "running"}
          <span class="loading-dot" aria-hidden="true"></span>
          <small>migrating storage</small>
        {/if}
      </div>
    </div>
  </header>
  {#if runtimeBlockingMessage}
    <div class="runtime-banner">
      {runtimeBlockingMessage}
    </div>
  {/if}

  <main id="main-content" class="grid">
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
        <button type="button" on:click={handleStartBackend} disabled={booting}>Start Backend</button>
        <button type="button" class="ghost" on:click={handleStopBackend} disabled={!backendManaged}>Stop Managed Backend</button>
        <button type="button" class="ghost" on:click={handleReconnect} disabled={booting || reconnectInFlight}>Reconnect</button>
      </div>
      <dl class="kv">
        <div>
          <dt>Backend Running</dt>
          <dd>{backendRunning ? "yes" : "no"}</dd>
        </div>
        <div>
          <dt>Engine State</dt>
          <dd role="status" aria-live="polite">{engineState}</dd>
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
        <button type="button" class="ghost" on:click={() => copyTranscript(lastTranscript)} disabled={!lastTranscript}>Copy</button>
        <button type="button" class="ghost" on:click={refreshHistory}>Refresh History</button>
      </div>
    </section>

    <section class="panel settings">
      <h2>Settings</h2>
      <div class="settings-grid">
        <div class="field-group">
          <h3>Hotkey</h3>
          <label for="hotkey-input">Push-to-talk key</label>
          <input id="hotkey-input" type="text" bind:value={hotkeyInput} />
          <button type="button" class="ghost" on:click={saveHotkey}>Save Hotkey</button>
        </div>

        <div class="field-group">
          <h3>Model</h3>
          {#if capabilities?.hardware}
            <p class="muted">
              {#if capabilities.hardware.gpu_available}
                {capabilities.hardware.gpu_name} ({capabilities.hardware.gpu_vram_gb.toFixed(1)}GB)
              {:else}
                {capabilities.hardware.gpu_name}
              {/if}
            </p>
          {/if}
          {#if modelDownloadState === "loading"}
            <p class="muted">Configuration locked during download</p>
          {/if}
          <label for="model-backend">Backend</label>
          <select
            id="model-backend"
            bind:value={modelBackend}
            disabled={modelDownloadState === "loading"}
            aria-label="Model backend"
            aria-invalid={validationErrors["backend"] ? true : undefined}
            aria-describedby={validationErrors["backend"] ? "err-backend" : undefined}
          >
            {#if capabilities}
              {#each capabilities.backends as backend}
                <option value={backend.id} disabled={!backend.available}>
                  {backend.label}{capabilities.recommendation?.backend === backend.id ? " (Recommended)" : ""}
                </option>
              {/each}
            {:else}
              <option value={modelBackend}>{modelBackend}</option>
            {/if}
          </select>
          {#if validationErrors["backend"]}
            <p id="err-backend" class="error-inline" role="alert">{validationErrors["backend"]}</p>
          {/if}
          <label for="model-name">Model</label>
          <select
            id="model-name"
            bind:value={modelName}
            disabled={modelDownloadState === "loading"}
            aria-label="Model name"
            aria-invalid={validationErrors["name"] ? true : undefined}
            aria-describedby={validationErrors["name"] ? "err-name" : undefined}
          >
            {#if capabilities?.model_presets?.[modelBackend]}
              {#if !capabilities.model_presets[modelBackend].includes(modelName)}
                <option value={modelName}>{modelName} (custom)</option>
              {/if}
              {#each capabilities.model_presets[modelBackend] as modelPreset}
                <option value={modelPreset}>
                  {modelPreset}{capabilities.recommendation?.name === modelPreset && capabilities.recommendation.backend === modelBackend ? " ★" : ""}
                </option>
              {/each}
            {:else}
              <option value={modelName}>{modelName}</option>
            {/if}
          </select>
          {#if capabilities?.recommendation && capabilities.recommendation.backend === modelBackend}
            <p class="muted">Recommended: {capabilities.recommendation.name}</p>
          {/if}
          {#if validationErrors["name"]}
            <p id="err-name" class="error-inline" role="alert">{validationErrors["name"]}</p>
          {/if}
          <label for="model-device">Device</label>
          <select
            id="model-device"
            bind:value={modelDevice}
            disabled={modelDownloadState === "loading"}
            aria-label="Compute device"
            aria-invalid={validationErrors["device"] ? true : undefined}
            aria-describedby={validationErrors["device"] ? "err-device" : undefined}
          >
            {#if capabilities?.model_devices}
              {#each capabilities.model_devices as device}
                <option value={device}>
                  {device}{capabilities.recommendation?.device === device && capabilities.recommendation.backend === modelBackend ? " (Recommended)" : ""}
                </option>
              {/each}
            {:else}
              <option value={modelDevice}>{modelDevice}</option>
            {/if}
          </select>
          {#if validationErrors["device"]}
            <p id="err-device" class="error-inline" role="alert">{validationErrors["device"]}</p>
          {/if}
          <label for="model-compute-type">Compute type</label>
          <select
            id="model-compute-type"
            bind:value={modelComputeType}
            disabled={modelDownloadState === "loading"}
            aria-label="Compute type"
            aria-invalid={validationErrors["compute_type"] ? true : undefined}
            aria-describedby={validationErrors["compute_type"] ? "err-compute-type" : undefined}
          >
            {#if capabilities?.compute_types?.[modelBackend]}
              {#each capabilities.compute_types[modelBackend] as computeType}
                <option value={computeType}>
                  {computeType}{capabilities.recommendation?.compute_type === computeType && capabilities.recommendation.backend === modelBackend ? " (Recommended)" : ""}
                </option>
              {/each}
            {:else if capabilities?.compute_types?.["auto"]}
              {#each capabilities.compute_types["auto"] as computeType}
                <option value={computeType}>
                  {computeType}{capabilities.recommendation?.compute_type === computeType && capabilities.recommendation.backend === modelBackend ? " (Recommended)" : ""}
                </option>
              {/each}
            {:else}
              <option value={modelComputeType}>{modelComputeType}</option>
            {/if}
          </select>
          {#if capabilities?.recommendation && capabilities.recommendation.backend === modelBackend}
            <p class="muted">{capabilities.recommendation.reason}</p>
          {/if}
          {#if validationErrors["compute_type"]}
            <p id="err-compute-type" class="error-inline" role="alert">{validationErrors["compute_type"]}</p>
          {/if}
          <p class="model-download-status {modelCacheStatus}">
            {#if modelCacheStatus === STATUS_READY}
              <span class="icon" aria-hidden="true">[ok]</span> Downloaded locally
            {:else if modelCacheStatus === STATUS_MISSING}
              <span class="icon" aria-hidden="true">[down]</span> Not downloaded locally
            {:else}
              <span class="icon" aria-hidden="true">[?]</span> Local cache state unknown
            {/if}
          </p>
          {#if selectedModelRequirement}
            <p class="model-requirement">
              Required: {formatBytes(selectedModelRequirement.remaining_bytes)} /
              Total: {formatBytes(selectedModelRequirement.estimated_total_bytes)} /
              Free: {formatBytes(selectedModelRequirement.disk_free_bytes)}
            </p>
          {/if}
          {#if modelDownloadState === "loading" || modelDownloadState === "error" || modelDownloadState === "completed"}
            <p class="model-download-detail {modelDownloadState}">{modelDownloadMessage || "-"}</p>
            <div class="progress-wrap">
              <progress max="100" value={modelDownloadProgressPct} aria-label="Model download: {modelDownloadProgressPct}%"></progress>
              <span aria-hidden="true">{modelDownloadProgressPct}%</span>
            </div>
            {#if modelDownloadBytesTotal !== null}
              <p class="model-download-detail">
                {formatBytes(modelDownloadBytesDone)} / {formatBytes(modelDownloadBytesTotal)}
                ({formatBytes(modelDownloadBytesRemaining)} remaining)
              </p>
            {/if}
          {/if}
          <button type="button" class="ghost" on:click={downloadSelectedModel} disabled={modelDownloadState === "loading"}>
            {modelDownloadState === "loading" ? "Downloading..." : "Download Model"}
          </button>
          <button type="button" class="ghost" on:click={saveModel} disabled={modelDownloadState === "loading"}>Save Model</button>
        </div>

        <div class="field-group">
          <h3>Audio</h3>
          <label for="audio-device">Input device</label>
          <input id="audio-device" type="text" bind:value={audioDevice} placeholder="default" />
          <label for="audio-sample-rate">Sample rate (Hz)</label>
          <input id="audio-sample-rate" type="number" bind:value={audioSampleRate} min="8000" max="96000" />
          <button type="button" class="ghost" on:click={saveAudio}>Save Audio</button>
        </div>

        <div class="field-group">
          <h3>Text Insertion</h3>
          <label class="checkbox">
            <input type="checkbox" bind:checked={textInsertionEnabled} />
            Enable text insertion
          </label>
          <button type="button" class="ghost" on:click={saveTextInsertion}>Save Text Insertion</button>
        </div>

        <div class="field-group">
          <h3>Storage</h3>
          <label for="storage-root">Storage Root</label>
          <input
            id="storage-root"
            type="text"
            bind:value={storageRootInput}
            placeholder="D:\\KeyvoxData"
            disabled={storageMigrationState === "running"}
          />
          <p class="muted">
            Changing storage root automatically migrates existing Keyvox data
            (models/history/exports/runtime) after checking destination free space.
          </p>
          <div class="button-row compact">
            <button type="button" class="ghost" on:click={browseStorageRoot}>Browse</button>
            <button type="button" class="ghost" on:click={applyStorageRoot} disabled={storageMigrationState === "running"}>
              {storageMigrationState === "running" ? "Migrating..." : "Apply Storage Root"}
            </button>
            <button type="button" class="ghost" on:click={refreshStorageStatus}>Refresh Storage</button>
          </div>
          {#if storageStatus}
            <p class="model-download-detail">
              Disk free: {formatBytes(storageStatus.disk_free_bytes)} | Migration required:
              {formatBytes(storageStatus.migration_estimate.bytes_required)}
            </p>
            <p class="model-download-detail">
              Models: {storageStatus.effective_paths.model_cache_root}
            </p>
            <p class="model-download-detail">
              History DB: {storageStatus.effective_paths.history_db}
            </p>
          {/if}
          {#if storageMigrationState !== "idle"}
            <p class="model-download-detail {storageMigrationState === 'error' ? 'error' : storageMigrationState === 'completed' ? 'completed' : 'loading'}">
              {storageMigrationMessage}
            </p>
            <div class="progress-wrap">
              <progress max="100" value={storageMigrationProgressPct} aria-label="Storage migration: {storageMigrationProgressPct}%"></progress>
              <span aria-hidden="true">{storageMigrationProgressPct}%</span>
            </div>
          {/if}
        </div>

        <div class="field-group">
          <h3>Dictionary <span class="badge">{Object.keys(dictionaryEntries).length}</span></h3>
          {#if Object.keys(dictionaryEntries).length === 0}
            <p class="muted">No dictionary entries. Add word corrections below.</p>
          {:else}
            <table class="dictionary-table">
              <thead>
                <tr>
                  <th scope="col">Pattern</th>
                  <th scope="col">Replacement</th>
                  <th scope="col"><span class="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {#each Object.entries(dictionaryEntries) as [key, value]}
                  <tr>
                    {#if dictEditingKey === key}
                      <td>{key}</td>
                      <td>
                        <input type="text" bind:value={dictEditingValue} />
                      </td>
                      <td>
                        <button type="button" class="ghost" on:click={() => updateDictionaryEntry(key, dictEditingValue)}>Save</button>
                        <button type="button" class="ghost" on:click={() => { dictEditingKey = null; dictEditingValue = ""; }}>Cancel</button>
                      </td>
                    {:else}
                      <td>{key}</td>
                      <td
                        role="button"
                        tabindex="0"
                        aria-label="Edit replacement for {key}"
                        on:click={() => { dictEditingKey = key; dictEditingValue = value; }}
                        on:keydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); dictEditingKey = key; dictEditingValue = value; } }}
                      >{value}</td>
                      <td>
                        <button type="button" class="ghost" on:click={() => deleteDictionaryEntry(key)}>Delete</button>
                      </td>
                    {/if}
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
          <div class="dictionary-add">
            <input type="text" bind:value={dictNewKey} placeholder="Pattern (e.g., 'keyvox')" aria-label="New dictionary pattern" />
            <input type="text" bind:value={dictNewValue} placeholder="Replacement (e.g., 'KeyVox')" aria-label="New dictionary replacement" />
            <button type="button" class="ghost" on:click={addDictionaryEntry}>Add</button>
          </div>
        </div>
      </div>
    </section>

    <section class="panel history">
      <div class="history-head">
        <h2>History</h2>
        <div class="button-row compact">
          <button type="button" class="ghost" on:click={clearHistory}>Clear</button>
          <select bind:value={exportFormat} aria-label="Export format">
            <option value="txt">TXT</option>
            <option value="csv">CSV</option>
          </select>
          <button type="button" class="ghost" on:click={exportHistory}>Export</button>
        </div>
      </div>

      <div class="history-search">
        <label for="history-search" class="sr-only">Search transcription history</label>
        <input
          id="history-search"
          type="text"
          bind:value={historySearch}
          placeholder="Search transcript text"
        />
        <button type="button" class="ghost" on:click={refreshHistory} aria-label="Search history">Search</button>
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
                <button type="button" class="ghost" on:click={() => copyTranscript(entry.text)}>Copy</button>
                <button type="button" class="ghost" on:click={() => deleteHistoryItem(entry.id)}>Delete</button>
              </div>
            </li>
          {/each}
        {/if}
      </ul>
    </section>
  </main>

  <aside class="notices" aria-live="polite" role="log" aria-label="Notifications">
    {#each notices as notice (notice.id)}
      <div class="notice {notice.level}" role="alert">
        <span>{notice.text}</span>
        <button type="button" class="notice-dismiss" on:click={() => dismissNotice(notice.id)} aria-label="Dismiss notification">×</button>
      </div>
    {/each}
  </aside>
</div>
