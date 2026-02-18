use serde::Serialize;
use std::env;
use std::ffi::OsString;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager, State};

#[derive(Default)]
struct BackendState {
    child: Mutex<Option<Child>>,
    port: Mutex<Option<u16>>,
    command: Mutex<Option<String>>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendStatus {
    running: bool,
    port: Option<u16>,
    managed: bool,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendPreflight {
    ok: bool,
    backend_command: String,
    executable_found: bool,
    port_valid: bool,
    issue_code: Option<String>,
    message: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct NvidiaInfo {
    gpu_name: String,
    cuda_version: String,
}

fn is_child_running(child: &mut Child) -> bool {
    matches!(child.try_wait(), Ok(None))
}

fn saved_install_keyvox_exe(app: &AppHandle) -> Option<PathBuf> {
    let pointer = app.path().app_data_dir().ok()?.join("install_path.txt");
    let dir = std::fs::read_to_string(pointer).ok()?;
    Some(PathBuf::from(dir.trim()).join("env").join("Scripts").join("keyvox.exe"))
}

fn default_venv_keyvox_exe(app: &AppHandle) -> Option<PathBuf> {
    Some(
        app.path()
            .app_data_dir()
            .ok()?
            .join("env")
            .join("Scripts")
            .join("keyvox.exe"),
    )
}

fn resolve_backend_command(app: &AppHandle, command: Option<String>) -> String {
    // 1. Explicit user override
    if let Some(cmd) = command.as_deref().map(str::trim).filter(|s| !s.is_empty()) {
        return cmd.to_string();
    }
    // 2. Saved install path (chosen by user in first-run setup)
    if let Some(exe) = saved_install_keyvox_exe(app) {
        if exe.is_file() {
            return exe.to_string_lossy().to_string();
        }
    }
    // 3. Default AppData venv location
    if let Some(exe) = default_venv_keyvox_exe(app) {
        if exe.is_file() {
            return exe.to_string_lossy().to_string();
        }
    }
    // 4. PATH fallback (developer / pip-install workflow)
    "keyvox".to_string()
}

fn has_path_components(binary: &str) -> bool {
    let path = Path::new(binary);
    path.is_absolute() || path.components().count() > 1
}

fn executable_candidates(binary: &str) -> Vec<OsString> {
    let mut candidates = vec![OsString::from(binary)];
    if cfg!(windows) && Path::new(binary).extension().is_none() {
        let pathext = env::var_os("PATHEXT").unwrap_or_else(|| OsString::from(".COM;.EXE;.BAT;.CMD"));
        for ext in pathext.to_string_lossy().split(';') {
            let normalized = ext.trim();
            if normalized.is_empty() {
                continue;
            }
            let suffix = if normalized.starts_with('.') {
                normalized.to_string()
            } else {
                format!(".{normalized}")
            };
            candidates.push(OsString::from(format!("{binary}{suffix}")));
        }
    }
    candidates
}

fn command_exists(binary: &str) -> bool {
    let trimmed = binary.trim();
    if trimmed.is_empty() {
        return false;
    }

    let candidates = executable_candidates(trimmed);

    if has_path_components(trimmed) {
        return candidates.iter().any(|candidate| PathBuf::from(candidate).is_file());
    }

    if candidates
        .iter()
        .any(|candidate| PathBuf::from(candidate).is_file())
    {
        return true;
    }

    if let Some(path_var) = env::var_os("PATH") {
        for dir in env::split_paths(&path_var) {
            for candidate in &candidates {
                if dir.join(candidate).is_file() {
                    return true;
                }
            }
        }
    }

    false
}

fn make_preflight(preferred_port: u16, backend_command: String) -> BackendPreflight {
    let executable_found = command_exists(&backend_command);
    let port_valid = preferred_port >= 1024;

    if !executable_found {
        return BackendPreflight {
            ok: false,
            backend_command,
            executable_found,
            port_valid,
            issue_code: Some("backend_command_not_found".to_string()),
            message: "Backend command not found. Add keyvox to PATH or set a full executable path in 'Backend Command'.".to_string(),
        };
    }

    if !port_valid {
        return BackendPreflight {
            ok: false,
            backend_command,
            executable_found,
            port_valid,
            issue_code: Some("invalid_port".to_string()),
            message: "Preferred port must be >= 1024.".to_string(),
        };
    }

    BackendPreflight {
        ok: true,
        backend_command,
        executable_found,
        port_valid,
        issue_code: None,
        message: "Backend preflight passed.".to_string(),
    }
}

fn refresh_child_state(
    child_guard: &mut Option<Child>,
    port_guard: &mut Option<u16>,
    command_guard: &mut Option<String>,
) -> bool {
    let running = match child_guard.as_mut() {
        Some(child) => is_child_running(child),
        None => false,
    };

    if !running {
        *child_guard = None;
        *port_guard = None;
        *command_guard = None;
    }

    running
}

#[tauri::command]
fn backend_status(state: State<'_, BackendState>) -> Result<BackendStatus, String> {
    let mut child_guard = state
        .child
        .lock()
        .map_err(|_| "Failed to lock backend process state".to_string())?;
    let mut port_guard = state
        .port
        .lock()
        .map_err(|_| "Failed to lock backend port state".to_string())?;
    let mut command_guard = state
        .command
        .lock()
        .map_err(|_| "Failed to lock backend command state".to_string())?;

    let running = refresh_child_state(&mut child_guard, &mut port_guard, &mut command_guard);

    Ok(BackendStatus {
        running,
        port: *port_guard,
        managed: running,
    })
}

#[tauri::command]
fn start_backend(
    app: AppHandle,
    state: State<'_, BackendState>,
    preferred_port: u16,
    command: Option<String>,
) -> Result<BackendStatus, String> {
    let mut child_guard = state
        .child
        .lock()
        .map_err(|_| "Failed to lock backend process state".to_string())?;
    let mut port_guard = state
        .port
        .lock()
        .map_err(|_| "Failed to lock backend port state".to_string())?;
    let mut command_guard = state
        .command
        .lock()
        .map_err(|_| "Failed to lock backend command state".to_string())?;

    if refresh_child_state(&mut child_guard, &mut port_guard, &mut command_guard) {
        return Ok(BackendStatus {
            running: true,
            port: *port_guard,
            managed: true,
        });
    }

    let binary = resolve_backend_command(&app, command);
    let preflight = make_preflight(preferred_port, binary.clone());
    if !preflight.ok {
        return Err(preflight.message);
    }

    let mut process = Command::new(&binary);
    process
        .arg("--server")
        .arg("--port")
        .arg(preferred_port.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    let child = process
        .spawn()
        .map_err(|err| format!("Failed to spawn backend '{binary}': {err}. Set 'Backend Command' to a valid executable path if needed."))?;

    *child_guard = Some(child);
    *port_guard = Some(preferred_port);
    *command_guard = Some(binary);

    Ok(BackendStatus {
        running: true,
        port: *port_guard,
        managed: true,
    })
}

#[tauri::command]
fn stop_backend(state: State<'_, BackendState>) -> Result<BackendStatus, String> {
    let mut child_guard = state
        .child
        .lock()
        .map_err(|_| "Failed to lock backend process state".to_string())?;
    let mut port_guard = state
        .port
        .lock()
        .map_err(|_| "Failed to lock backend port state".to_string())?;
    let mut command_guard = state
        .command
        .lock()
        .map_err(|_| "Failed to lock backend command state".to_string())?;

    if let Some(mut child) = child_guard.take() {
        match child.try_wait() {
            Ok(Some(_)) => {}
            Ok(None) | Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }

    *port_guard = None;
    *command_guard = None;

    Ok(BackendStatus {
        running: false,
        port: None,
        managed: false,
    })
}

#[tauri::command]
fn backend_preflight(app: AppHandle, preferred_port: u16, command: Option<String>) -> BackendPreflight {
    make_preflight(preferred_port, resolve_backend_command(&app, command))
}

#[tauri::command]
fn pick_storage_folder() -> Option<String> {
    rfd::FileDialog::new()
        .pick_folder()
        .map(|path| path.display().to_string())
}

#[tauri::command]
fn set_tray_status(app: AppHandle, tooltip: String) -> Result<(), String> {
    if let Some(tray) = app.tray_by_id("main") {
        tray.set_tooltip(Some(tooltip))
            .map_err(|err| format!("Failed to set tray tooltip: {err}"))?;
    }
    Ok(())
}

#[tauri::command]
fn get_default_install_dir(app: AppHandle) -> Result<String, String> {
    app.path()
        .app_data_dir()
        .map(|p: std::path::PathBuf| p.to_string_lossy().to_string())
        .map_err(|e: tauri::Error| e.to_string())
}

#[tauri::command]
fn detect_nvidia() -> Option<NvidiaInfo> {
    let output = Command::new("nvidia-smi").output().ok()?;
    if !output.status.success() {
        return None;
    }
    let stdout = String::from_utf8_lossy(&output.stdout);

    // Parse "CUDA Version: 12.4" from nvidia-smi header
    let cuda_version = stdout
        .lines()
        .find_map(|line| {
            let pos = line.find("CUDA Version:")?;
            Some(line[pos + "CUDA Version:".len()..].trim().to_string())
        })?;

    // Query GPU name
    let name_out = Command::new("nvidia-smi")
        .args(["--query-gpu=name", "--format=csv,noheader"])
        .output()
        .ok()?;
    let gpu_name = String::from_utf8_lossy(&name_out.stdout)
        .lines()
        .next()
        .unwrap_or("Unknown GPU")
        .trim()
        .to_string();

    Some(NvidiaInfo { gpu_name, cuda_version })
}

fn run_uv_streaming_sync(
    app: &AppHandle,
    uv_exe: &Path,
    args: &[&str],
) -> Result<(), String> {
    let mut child = Command::new(uv_exe)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to spawn uv: {e}"))?;

    // Drain stdout in a background thread (prevents pipe buffer deadlock)
    if let Some(stdout) = child.stdout.take() {
        std::thread::spawn(move || {
            let _ = BufReader::new(stdout).lines().count();
        });
    }

    // Stream stderr lines to frontend as Tauri events
    if let Some(stderr) = child.stderr.take() {
        let app_clone = app.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().flatten() {
                let _ = app_clone.emit("backend-install-progress", &line);
            }
        });
    }

    let status = child.wait().map_err(|e| e.to_string())?;
    if !status.success() {
        return Err(format!("uv exited with status {status}"));
    }
    Ok(())
}

#[tauri::command]
async fn install_backend(
    app: AppHandle,
    stack: String,
    install_dir: String,
) -> Result<(), String> {
    let resource_dir = app.path().resource_dir().map_err(|e: tauri::Error| e.to_string())?;
    let resources = resource_dir.join("resources");

    let uv_exe = resources.join("uv.exe");
    if !uv_exe.is_file() {
        return Err("uv.exe not found in resources — this build may not include the installer.".to_string());
    }

    // Find keyvox wheel in resources/
    let wheel = std::fs::read_dir(&resources)
        .map_err(|e| e.to_string())?
        .find_map(|entry| {
            let path = entry.ok()?.path();
            let name = path.file_name()?.to_str()?.to_string();
            if name.starts_with("keyvox-") && name.ends_with(".whl") {
                Some(path)
            } else {
                None
            }
        })
        .ok_or("keyvox wheel not found in resources")?;

    let install_path = PathBuf::from(&install_dir);
    let venv_dir = install_path.join("env");
    let python_exe = venv_dir.join("Scripts").join("python.exe");

    let torch_index = if stack == "gpu" {
        "https://download.pytorch.org/whl/cu124"
    } else {
        "https://download.pytorch.org/whl/cpu"
    };

    let extras = if stack == "gpu" {
        "nvidia,singleton,server"
    } else {
        "singleton,server"
    };
    let wheel_spec = format!("{}[{}]", wheel.display(), extras);

    let uv_str = uv_exe.to_string_lossy().to_string();
    let venv_str = venv_dir.to_string_lossy().to_string();
    let python_str = python_exe.to_string_lossy().to_string();

    // Step 1: create venv
    run_uv_streaming_sync(&app, &uv_exe, &["venv", &venv_str, "--python", "3.11"])?;

    // Step 2: install torch
    run_uv_streaming_sync(
        &app,
        &uv_exe,
        &[
            "pip", "install",
            "--python", &python_str,
            "torch",
            "--index-url", torch_index,
        ],
    )?;

    // Step 3: install keyvox wheel
    run_uv_streaming_sync(
        &app,
        &uv_exe,
        &["pip", "install", "--python", &python_str, &wheel_spec],
    )?;

    // Save install path so resolve_backend_command can find it on next launch
    let app_data = app.path().app_data_dir().map_err(|e: tauri::Error| e.to_string())?;
    std::fs::create_dir_all(&app_data).map_err(|e| e.to_string())?;
    std::fs::write(app_data.join("install_path.txt"), install_dir.trim())
        .map_err(|e| e.to_string())?;

    // Emit a final completion event
    let _ = app.emit("backend-install-progress", "[Keyvox] Installation complete.");

    // Suppress unused variable warning
    let _ = uv_str;

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let show_hide = MenuItem::with_id(app, "show_hide", "Show / Hide", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_hide, &quit])?;

            let mut tray_builder = TrayIconBuilder::with_id("main")
                .tooltip("Keyvox Desktop")
                .menu(&menu)
                .menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show_hide" => {
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                });

            if let Some(icon) = app.default_window_icon().cloned() {
                tray_builder = tray_builder.icon(icon);
            }
            tray_builder
                .build(app)
                .map_err(|err| -> Box<dyn std::error::Error> { Box::new(err) })?;
            Ok(())
        })
        .manage(BackendState::default())
        .invoke_handler(tauri::generate_handler![
            backend_status,
            backend_preflight,
            start_backend,
            stop_backend,
            pick_storage_folder,
            set_tray_status,
            get_default_install_dir,
            detect_nvidia,
            install_backend,
        ])
        .run(tauri::generate_context!())
        .expect("error while running keyvox desktop app");
}
