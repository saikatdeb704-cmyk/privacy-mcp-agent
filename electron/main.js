import { app, BrowserWindow } from 'electron';
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let backendProcess;
let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    title: 'Privacy MCP Agent',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true
    },
    autoHideMenuBar: true
  });

  // Load the FastAPI server
  // We'll give the backend a few seconds to start, or poll it
  const loadURL = () => {
    mainWindow.loadURL('http://127.0.0.1:8000').catch(() => {
      setTimeout(loadURL, 500);
    });
  };
  loadURL();

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  // Determine path to backend executable or python script
  // In production (packaged), we use the compiled exe
  const isDev = !app.isPackaged;
  
  if (isDev) {
    const pythonPath = path.join(__dirname, '..', 'backend', '.venv', 'Scripts', 'python.exe');
    const mainScript = path.join(__dirname, '..', 'backend', 'main.py');
    backendProcess = spawn(pythonPath, [mainScript], {
      cwd: path.join(__dirname, '..', 'backend'),
      stdio: 'inherit'
    });
  } else {
    // In production, we expect the backend.exe to be shipped alongside the app
    const exePath = path.join(process.resourcesPath, 'backend.exe');
    backendProcess = spawn(exePath, [], {
      stdio: 'inherit'
    });
  }

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('quit', () => {
  if (backendProcess) {
    backendProcess.kill();
  }
});
