<script lang="ts">
  import { onMount } from "svelte";
  import { detectNvidia, installBackend, getDefaultInstallDir, pickStorageFolder } from "./backend";
  import type { NvidiaInfo } from "./backend";

  export let onComplete: () => void;

  type State = "detecting" | "choice" | "installing" | "done" | "error";
  let state: State = "detecting";
  let nvidia: NvidiaInfo | null = null;
  let progressLines: string[] = [];
  let errorMessage = "";
  let installDir = "";

  onMount(async () => {
    try {
      installDir = await getDefaultInstallDir();
    } catch {
      installDir = "";
    }
    try {
      nvidia = await detectNvidia();
    } catch {
      nvidia = null;
    }
    state = "choice";
  });

  async function changeFolder() {
    const picked = await pickStorageFolder();
    if (picked) installDir = picked;
  }

  async function install(stack: "gpu" | "cpu") {
    state = "installing";
    progressLines = [];
    try {
      await installBackend(stack, installDir, (line) => {
        progressLines = [...progressLines, line];
      });
      state = "done";
      setTimeout(onComplete, 1500);
    } catch (e) {
      errorMessage = String(e);
      state = "error";
    }
  }
</script>

<div class="first-run-overlay">
  <div class="first-run-card">
    <div class="first-run-header">
      <span class="mic-icon" aria-hidden="true">🎤</span>
      <div>
        <h1>Keyvox — First-time setup</h1>
        <p class="subtitle">Install the voice engine to get started.</p>
      </div>
    </div>

    {#if state === "detecting"}
      <p class="detecting-msg">Detecting hardware…</p>

    {:else if state === "choice"}
      <div class="install-location">
        <label for="install-dir">Install location</label>
        <div class="install-dir-row">
          <span class="folder-icon" aria-hidden="true">📁</span>
          <span class="install-dir-text">{installDir || "Default location"}</span>
          <button type="button" class="ghost" on:click={changeFolder}>Change folder…</button>
        </div>
      </div>

      <div class="stack-cards">
        {#if nvidia}
          <button
            type="button"
            class="stack-card gpu"
            on:click={() => install("gpu")}
            aria-label="Install GPU stack — NVIDIA {nvidia.gpu_name}, CUDA {nvidia.cuda_version}"
          >
            <div class="stack-card-title">
              <span aria-hidden="true">⚡</span>
              GPU stack
              <span class="badge recommended">Recommended</span>
            </div>
            <div class="stack-card-detail">NVIDIA {nvidia.gpu_name} · CUDA {nvidia.cuda_version}</div>
            <div class="stack-card-size">~2.8 GB download · fastest transcription speed</div>
            <div class="stack-card-disk">~4.5 GB total on disk (including model)</div>
          </button>
        {/if}

        <button
          type="button"
          class="stack-card cpu"
          on:click={() => install("cpu")}
          aria-label="Install CPU-only stack — works on any machine"
        >
          <div class="stack-card-title">
            <span aria-hidden="true">🖥</span>
            CPU only
            {#if !nvidia}<span class="badge">Only option (no NVIDIA GPU detected)</span>{/if}
          </div>
          <div class="stack-card-detail">Works on any machine</div>
          <div class="stack-card-size">~400 MB download · slower transcription speed</div>
          <div class="stack-card-disk">~600 MB total on disk (including model)</div>
        </button>
      </div>

      <p class="model-note">
        After install, Keyvox downloads a Whisper model on first use
        ({nvidia ? "~1.5 GB for large-v3-turbo" : "~150 MB for tiny"}).
        It is stored in the same install folder.
      </p>

    {:else if state === "installing"}
      <p class="installing-msg">Installing… this may take several minutes depending on your connection.</p>
      <div class="progress-log" role="log" aria-live="polite" aria-label="Installation progress">
        {#each progressLines as line}
          <div class="log-line">{line}</div>
        {/each}
      </div>

    {:else if state === "done"}
      <div class="done-msg">
        <span aria-hidden="true">✅</span>
        Setup complete! Starting Keyvox…
      </div>

    {:else if state === "error"}
      <div class="error-msg">
        <p><strong>Installation failed.</strong></p>
        <pre class="error-detail">{errorMessage}</pre>
        <button type="button" on:click={() => { state = "choice"; progressLines = []; }}>
          Try again
        </button>
      </div>
    {/if}
  </div>
</div>

<style>
  .first-run-overlay {
    position: fixed;
    inset: 0;
    background: var(--bg, #0f0f13);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .first-run-card {
    background: var(--surface, #1a1a24);
    border: 1px solid var(--border, #2a2a3a);
    border-radius: 12px;
    padding: 2rem;
    width: min(520px, 90vw);
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .first-run-header {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .mic-icon {
    font-size: 2rem;
  }

  h1 {
    font-size: 1.25rem;
    font-weight: 600;
    margin: 0 0 0.25rem;
  }

  .subtitle {
    margin: 0;
    color: var(--muted, #888);
    font-size: 0.9rem;
  }

  .detecting-msg,
  .installing-msg {
    color: var(--muted, #888);
    font-size: 0.9rem;
  }

  .install-location {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .install-location label {
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--muted, #888);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .install-dir-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--input-bg, #0f0f13);
    border: 1px solid var(--border, #2a2a3a);
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
  }

  .install-dir-text {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: monospace;
  }

  .stack-cards {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .stack-card {
    background: var(--input-bg, #0f0f13);
    border: 1px solid var(--border, #2a2a3a);
    border-radius: 8px;
    padding: 1rem;
    text-align: left;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .stack-card:hover,
  .stack-card:focus-visible {
    border-color: var(--accent, #7c6fcd);
    background: var(--surface-hover, #22222e);
    outline: none;
  }

  .stack-card.gpu {
    border-color: var(--accent, #7c6fcd);
  }

  .stack-card-title {
    font-weight: 600;
    font-size: 1rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .stack-card-detail {
    font-size: 0.875rem;
    color: var(--muted, #888);
  }

  .stack-card-size {
    font-size: 0.8rem;
    color: var(--muted, #888);
  }

  .stack-card-disk {
    font-size: 0.75rem;
    color: var(--muted, #666);
  }

  .badge {
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.1em 0.4em;
    border-radius: 4px;
    background: var(--accent, #7c6fcd);
    color: #fff;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }

  .badge.recommended {
    background: var(--accent, #7c6fcd);
  }

  .model-note {
    font-size: 0.8rem;
    color: var(--muted, #888);
    border-left: 3px solid var(--border, #2a2a3a);
    padding-left: 0.75rem;
    margin: 0;
  }

  .progress-log {
    background: var(--input-bg, #0f0f13);
    border: 1px solid var(--border, #2a2a3a);
    border-radius: 6px;
    padding: 0.75rem;
    height: 220px;
    overflow-y: auto;
    font-family: monospace;
    font-size: 0.78rem;
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
  }

  .log-line {
    white-space: pre-wrap;
    word-break: break-all;
    color: var(--muted, #aaa);
  }

  .done-msg {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 1.1rem;
    font-weight: 500;
    color: #4ade80;
  }

  .error-msg {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .error-detail {
    background: var(--input-bg, #0f0f13);
    border: 1px solid var(--border, #2a2a3a);
    border-radius: 6px;
    padding: 0.75rem;
    font-size: 0.78rem;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 160px;
    overflow-y: auto;
    color: #f87171;
  }

  .ghost {
    background: transparent;
    border: 1px solid var(--border, #2a2a3a);
    border-radius: 4px;
    color: inherit;
    cursor: pointer;
    font-size: 0.8rem;
    padding: 0.25rem 0.6rem;
    transition: border-color 0.15s;
  }

  .ghost:hover {
    border-color: var(--accent, #7c6fcd);
  }
</style>
