use anyhow::{bail, Context, Result};
use std::path::Path;
use tokio::process::Child;

pub struct Sidecar {
    _child: Child,
}

/// Spawn the Python sidecar and wait until it is accepting connections.
/// Respects the `PYTHON_EXECUTABLE` env var (defaults to `python3`).
/// Also checks for virtualenv at .venv/ or venv/ in project_root or Mimir dir.
pub async fn spawn(project_root: &Path, port: u16) -> Result<Sidecar> {
    // Determine Mimir directory for PYTHONPATH
    let sidecar_script = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .context("no parent of CARGO_MANIFEST_DIR")?
        .join("sidecar")
        .join("sidecar.py");

    let mimir_dir = sidecar_script
        .parent()
        .and_then(|p| p.parent())
        .and_then(|p| p.parent())
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| project_root.to_path_buf());

    // Find the right Python executable
    // Priority: PYTHON_EXECUTABLE env var > .venv in project > .venv in Mimir > system python3
    let python = if let Ok(py) = std::env::var("PYTHON_EXECUTABLE") {
        py
    } else if project_root.join(".venv").exists() {
        project_root
            .join(".venv")
            .join("bin")
            .join("python")
            .to_string_lossy()
            .to_string()
    } else if mimir_dir.join(".venv").exists() {
        mimir_dir
            .join(".venv")
            .join("bin")
            .join("python")
            .to_string_lossy()
            .to_string()
    } else {
        "python3".to_string()
    };

    tracing::info!(
        "Spawning Python sidecar: {} {} --port {}",
        python,
        sidecar_script.display(),
        port
    );

    let pythonpath = std::env::var("PYTHONPATH").unwrap_or_default();
    let new_pythonpath = if pythonpath.is_empty() {
        mimir_dir.to_string_lossy().to_string()
    } else {
        format!("{}:{}", mimir_dir.display(), pythonpath)
    };

    let child = tokio::process::Command::new(&python)
        .arg(&sidecar_script)
        .arg("--port")
        .arg(port.to_string())
        .env("PROJECT_ROOT", project_root)
        .env("PYTHONPATH", &new_pythonpath)
        .kill_on_drop(true)
        .spawn()
        .with_context(|| {
            format!(
                "Failed to spawn Python sidecar. Is '{}' on your PATH and is the \
                 virtualenv/conda env active? Set PYTHON_EXECUTABLE to override.",
                python
            )
        })?;

    // Poll health endpoint until ready (up to 20 s)
    let health_url = format!("http://127.0.0.1:{}/health", port);
    let http = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .build()?;

    for attempt in 0..40 {
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        if http.get(&health_url).send().await.is_ok() {
            tracing::info!("Python sidecar ready on port {}", port);
            return Ok(Sidecar { _child: child });
        }
        if attempt == 3 {
            tracing::info!("Still waiting for Python sidecar...");
        }
    }

    bail!("Python sidecar did not become ready within 20 seconds")
}
