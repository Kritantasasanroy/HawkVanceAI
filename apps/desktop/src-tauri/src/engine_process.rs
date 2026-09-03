//! The local engine, run as a child process and spoken to over its standard input and output.
//!
//! Deliberately not an HTTP server on a port. A port is an attack surface, something a firewall
//! has to be told about, and something another program on the machine could talk to. A pipe to a
//! child process is none of those.
//!
//! One JSON object per line goes in, one comes back. The child writes its logs to standard error
//! so that a chatty dependency printing something cannot corrupt the protocol.

use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Mutex;

use serde::Serialize;
use serde_json::{json, Value};

#[derive(Debug, thiserror::Error)]
pub enum EngineError {
    #[error("engine_not_installed")]
    NotInstalled,
    #[error("the local engine stopped responding")]
    Unavailable,
    #[error("{0}")]
    Failed(String),
}

impl EngineError {
    /// The shape the web view expects, so a failure can be told apart from a missing install
    /// without parsing the message text.
    pub fn as_payload(&self) -> Value {
        match self {
            EngineError::NotInstalled => json!({
                "code": "engine_not_installed",
                "message": "The local reading engine is not installed with this copy of HawkVance."
            }),
            EngineError::Unavailable => json!({
                "code": "engine_unavailable",
                "message": "The local processing engine did not respond. Restart HawkVance and try again."
            }),
            EngineError::Failed(message) => json!({
                "code": "engine_error",
                "message": message
            }),
        }
    }
}

struct Running {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

#[derive(Default)]
pub struct EngineProcess {
    running: Mutex<Option<Running>>,
}

impl EngineProcess {
    pub fn new() -> Self {
        Self::default()
    }

    /// Sends one request and waits for its reply.
    pub fn request<T: Serialize>(&self, method: &str, params: &T) -> Result<Value, EngineError> {
        let mut guard = self.running.lock().map_err(|_| EngineError::Unavailable)?;
        if guard.is_none() {
            *guard = Some(Self::spawn()?);
        }

        let running = guard.as_mut().ok_or(EngineError::Unavailable)?;
        let request = json!({ "id": 1, "method": method, "params": params });

        let outcome = (|| -> Result<Value, EngineError> {
            writeln!(running.stdin, "{request}").map_err(|_| EngineError::Unavailable)?;
            running.stdin.flush().map_err(|_| EngineError::Unavailable)?;

            // Log lines share the pipe's sibling, not this one, but a dependency that writes to
            // standard output anyway would land here. Anything that is not a reply to this request
            // is skipped rather than treated as one.
            loop {
                let mut line = String::new();
                let read = running
                    .stdout
                    .read_line(&mut line)
                    .map_err(|_| EngineError::Unavailable)?;
                if read == 0 {
                    return Err(EngineError::Unavailable);
                }
                let Ok(value) = serde_json::from_str::<Value>(line.trim()) else {
                    continue;
                };
                if value.get("id").is_none() {
                    continue;
                }
                if value.get("ok").and_then(Value::as_bool) == Some(true) {
                    return Ok(value.get("result").cloned().unwrap_or(Value::Null));
                }
                let message = value
                    .get("error")
                    .and_then(|error| error.get("message"))
                    .and_then(Value::as_str)
                    .unwrap_or("The local engine could not complete that.")
                    .to_string();
                return Err(EngineError::Failed(message));
            }
        })();

        // A broken pipe means the child is gone. Dropping it here means the next call starts a
        // fresh one instead of writing into a dead handle forever.
        if matches!(outcome, Err(EngineError::Unavailable)) {
            if let Some(mut dead) = guard.take() {
                let _ = dead.child.kill();
            }
        }
        outcome
    }

    fn spawn() -> Result<Running, EngineError> {
        let mut last = EngineError::NotInstalled;

        for (program, arguments) in Self::candidates() {
            if !program.exists() {
                continue;
            }
            let mut command = Command::new(&program);
            command
                .args(&arguments)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::null());

            // Without this a console window flashes up on every launch on Windows.
            #[cfg(windows)]
            {
                use std::os::windows::process::CommandExt;
                const CREATE_NO_WINDOW: u32 = 0x0800_0000;
                command.creation_flags(CREATE_NO_WINDOW);
            }

            // `python -m hawkvance_engine` only resolves from the package root, so the child is
            // given that directory to start in.
            if !arguments.is_empty() {
                if let Some(root) = Self::package_root(&program) {
                    command.current_dir(root);
                }
            }

            match command.spawn() {
                Ok(mut child) => {
                    let Some(stdin) = child.stdin.take() else {
                        last = EngineError::Unavailable;
                        continue;
                    };
                    let Some(stdout) = child.stdout.take() else {
                        last = EngineError::Unavailable;
                        continue;
                    };
                    return Ok(Running {
                        child,
                        stdin,
                        stdout: BufReader::new(stdout),
                    });
                }
                Err(_) => last = EngineError::Unavailable,
            }
        }
        Err(last)
    }

    /// From `.../apps/engine/.venv/Scripts/python.exe` back up to `.../apps/engine`.
    fn package_root(program: &std::path::Path) -> Option<PathBuf> {
        program
            .parent()
            .and_then(|scripts| scripts.parent())
            .and_then(|venv| venv.parent())
            .map(PathBuf::from)
    }

    /// Where to look for the engine, in the order it should be preferred.
    ///
    /// A release binary launched from Explorer inherits whatever working directory Explorer felt
    /// like using, so nothing here may depend on the current directory. The repository is found by
    /// walking up from the executable instead.
    fn candidates() -> Vec<(PathBuf, Vec<String>)> {
        let mut found = Vec::new();
        let module = vec!["-m".to_string(), "hawkvance_engine".to_string()];

        if let Ok(current) = std::env::current_exe() {
            if let Some(directory) = current.parent() {
                // Where the Tauri bundler places the frozen sidecar.
                found.push((directory.join("engine").join("hawkvance-engine.exe"), Vec::new()));
                found.push((directory.join("hawkvance-engine.exe"), Vec::new()));

                let mut ancestor = Some(directory);
                for _ in 0..7 {
                    let Some(level) = ancestor else { break };
                    let engine = level.join("apps").join("engine");
                    if engine.is_dir() {
                        found.push((
                            engine.join(".venv").join("Scripts").join("python.exe"),
                            module.clone(),
                        ));
                        found.push((engine.join(".venv").join("bin").join("python"), module.clone()));
                    }
                    ancestor = level.parent();
                }
            }
        }

        // An explicit override always wins, for anyone running a non-standard setup.
        if let Ok(override_path) = std::env::var("HAWKVANCE_ENGINE_PYTHON") {
            found.insert(0, (PathBuf::from(override_path), module.clone()));
        }

        found
    }

    pub fn shutdown(&self) {
        if let Ok(mut guard) = self.running.lock() {
            if let Some(mut running) = guard.take() {
                let _ = running.child.kill();
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_frozen_sidecar_is_preferred_over_a_development_environment() {
        let candidates = EngineProcess::candidates();
        let first = candidates.first().expect("at least one candidate");
        assert!(
            first.0.ends_with("hawkvance-engine.exe"),
            "the packaged engine must be tried before any development one"
        );
        assert!(first.1.is_empty(), "the frozen sidecar takes no module argument");
    }

    #[test]
    fn an_override_is_tried_before_everything_else() {
        std::env::set_var("HAWKVANCE_ENGINE_PYTHON", "C:/custom/python.exe");
        let candidates = EngineProcess::candidates();
        std::env::remove_var("HAWKVANCE_ENGINE_PYTHON");

        assert_eq!(candidates[0].0, PathBuf::from("C:/custom/python.exe"));
        assert_eq!(candidates[0].1, vec!["-m", "hawkvance_engine"]);
    }

    #[test]
    fn a_missing_engine_reports_that_rather_than_a_generic_failure() {
        // The web view shows a setup step for this, not an error, so the distinction has to
        // survive the trip across the boundary.
        let payload = EngineError::NotInstalled.as_payload();
        assert_eq!(payload["code"], "engine_not_installed");
    }

    #[test]
    fn a_failure_message_reaches_the_caller_intact() {
        let payload = EngineError::Failed("cannot read that file yet".into()).as_payload();
        assert_eq!(payload["code"], "engine_error");
        assert_eq!(payload["message"], "cannot read that file yet");
    }

    #[test]
    fn the_package_root_is_two_levels_above_the_interpreter() {
        let interpreter = PathBuf::from("/repo/apps/engine/.venv/Scripts/python.exe");
        let root = EngineProcess::package_root(&interpreter).expect("resolves");
        assert!(root.ends_with("engine"));
    }
}
