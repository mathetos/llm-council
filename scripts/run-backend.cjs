/**
 * Start the FastAPI backend using the project .venv (no "python -m uv" required).
 */
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

const root = path.join(__dirname, "..");
const isWin = process.platform === "win32";
const py = isWin
  ? path.join(root, ".venv", "Scripts", "python.exe")
  : path.join(root, ".venv", "bin", "python");

if (!fs.existsSync(py)) {
  console.error("Missing virtualenv Python at:", py);
  console.error("From the project root run:  uv sync");
  process.exit(1);
}

const child = spawn(py, ["-m", "backend.main"], {
  cwd: root,
  stdio: "inherit",
  shell: false,
});

child.on("exit", (code, signal) => {
  if (signal) process.exit(1);
  process.exit(code ?? 0);
});
