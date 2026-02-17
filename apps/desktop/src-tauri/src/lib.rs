use serde::Serialize;
use std::env;
use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::State;

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

fn is_child_running(child: &mut Child) -> bool {
    matches!(child.try_wait(), Ok(None))
}

fn resolve_backend_command(command: Option<String>) -> String {
    command
        .as_deref()
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .unwrap_or("keyvox")
        .to_string()
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

    let binary = resolve_backend_command(command);
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
fn backend_preflight(preferred_port: u16, command: Option<String>) -> BackendPreflight {
    make_preflight(preferred_port, resolve_backend_command(command))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendState::default())
        .invoke_handler(tauri::generate_handler![
            backend_status,
            backend_preflight,
            start_backend,
            stop_backend
        ])
        .run(tauri::generate_context!())
        .expect("error while running keyvox desktop app");
}
