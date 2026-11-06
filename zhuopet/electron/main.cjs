const { app, BrowserWindow, Tray, Menu, ipcMain, globalShortcut, nativeImage, screen } = require('electron');
const path = require('node:path');
const fs = require('node:fs');

const isDev = !app.isPackaged;
const stateFile = path.join(app.getPath('userData'), 'window-state.json');

let mainWindow = null;
let petWindow = null;
let tray = null;
let forceQuit = false;
let clickThrough = false;

function loadState() {
  try {
    return JSON.parse(fs.readFileSync(stateFile, 'utf8'));
  } catch {
    return {};
  }
}

function saveState() {
  try {
    const state = {
      main: mainWindow && !mainWindow.isDestroyed() ? mainWindow.getBounds() : undefined,
      pet: petWindow && !petWindow.isDestroyed() ? petWindow.getBounds() : undefined,
    };
    fs.writeFileSync(stateFile, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

function appUrl(mode) {
  if (isDev) return `http://localhost:5173/?mode=${mode}`;
  return path.join(__dirname, '..', 'dist', 'index.html');
}

function load(win, mode) {
  if (isDev) {
    win.loadURL(appUrl(mode));
  } else {
    win.loadFile(appUrl(mode), { search: `?mode=${mode}` });
  }
}

function createMainWindow() {
  const state = loadState();
  const bounds = state.main ?? {};
  mainWindow = new BrowserWindow({
    width: bounds.width || 1280,
    height: bounds.height || 820,
    x: bounds.x,
    y: bounds.y,
    minWidth: 960,
    minHeight: 680,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    alwaysOnTop: true,
    title: 'ZhuoPet',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.setAlwaysOnTop(true, 'screen-saver');
  load(mainWindow, 'app');

  mainWindow.on('close', (event) => {
    if (!forceQuit) {
      event.preventDefault();
      mainWindow.hide();
      saveState();
    }
  });
  mainWindow.on('closed', () => {
    saveState();
    mainWindow = null;
  });
  mainWindow.on('moved', saveState);
  mainWindow.on('resized', saveState);
}

function createPetWindow() {
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.show();
    return;
  }
  const state = loadState();
  const bounds = state.pet ?? {};
  petWindow = new BrowserWindow({
    width: bounds.width || 460,
    height: bounds.height || 760,
    x: bounds.x,
    y: bounds.y,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    hasShadow: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: true,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });
  petWindow.once('ready-to-show', () => petWindow.show());
  petWindow.setAlwaysOnTop(true, 'screen-saver');
  petWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  load(petWindow, 'pet');
  petWindow.on('moved', saveState);
  petWindow.on('resized', saveState);
  petWindow.on('closed', () => {
    petWindow = null;
    saveState();
  });
}

function togglePetWindow() {
  if (!petWindow || petWindow.isDestroyed()) {
    createPetWindow();
    return;
  }
  if (petWindow.isVisible()) petWindow.hide();
  else petWindow.show();
}

function setPetClickThrough(value) {
  clickThrough = value;
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.setIgnoreMouseEvents(value, { forward: true });
  }
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('pet:click-through', value);
  }
  rebuildTray();
}

function sendToMain(channel) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.show();
    mainWindow.focus();
    mainWindow.webContents.send(channel);
  }
}

function rebuildTray() {
  if (!tray) return;
  const menu = Menu.buildFromTemplate([
    { label: '显示主窗口', click: () => { mainWindow?.show(); mainWindow?.focus(); } },
    { label: '小窗桌宠', click: togglePetWindow },
    { type: 'separator' },
    { label: '打开聊天', click: () => sendToMain('pet:open-chat') },
    { label: '设置', click: () => sendToMain('pet:open-settings') },
    { label: '模型工坊', click: () => sendToMain('pet:open-studio') },
    { type: 'separator' },
    {
      label: clickThrough ? '关闭鼠标穿透' : '开启鼠标穿透',
      click: () => setPetClickThrough(!clickThrough),
    },
    {
      label: '总在最前',
      type: 'checkbox',
      checked: mainWindow ? mainWindow.isAlwaysOnTop() : true,
      click: (item) => {
        const next = !item.checked;
        mainWindow?.setAlwaysOnTop(next, 'screen-saver');
        petWindow?.setAlwaysOnTop(next, 'screen-saver');
        rebuildTray();
      },
    },
    { type: 'separator' },
    { label: '退出 ZhuoPet', click: () => { forceQuit = true; app.quit(); } },
  ]);
  tray.setContextMenu(menu);
}

function createTray() {
  const iconPath = path.join(__dirname, 'tray.png');
  const image = fs.existsSync(iconPath) ? nativeImage.createFromPath(iconPath) : nativeImage.createEmpty();
  tray = new Tray(image);
  tray.setToolTip('ZhuoPet · 你的 AI 桌宠');
  tray.on('click', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) mainWindow.focus();
      else mainWindow.show();
    }
  });
  rebuildTray();
}

ipcMain.on('pet:quit', () => {
  forceQuit = true;
  app.quit();
});
ipcMain.on('pet:ignore', (_event, value) => setPetClickThrough(Boolean(value)));
ipcMain.on('pet:always-on-top', (_event, value) => {
  mainWindow?.setAlwaysOnTop(Boolean(value), 'screen-saver');
  petWindow?.setAlwaysOnTop(Boolean(value), 'screen-saver');
  rebuildTray();
});
ipcMain.on('pet:minimize', () => mainWindow?.minimize());
ipcMain.on('pet:toggle-pet', togglePetWindow);
ipcMain.on('pet:open-chat', () => sendToMain('pet:open-chat'));
ipcMain.on('pet:open-settings', () => sendToMain('pet:open-settings'));

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    if (process.platform === 'win32') {
      app.commandLine.appendSwitch('enable-transparent-visuals');
    }
    createMainWindow();
    createPetWindow();
    createTray();

    globalShortcut.register('CommandOrControl+Alt+Z', () => {
      if (!mainWindow) return;
      if (mainWindow.isVisible()) mainWindow.hide();
      else {
        mainWindow.show();
        mainWindow.focus();
      }
    });
    globalShortcut.register('CommandOrControl+Alt+T', () => setPetClickThrough(!clickThrough));
    globalShortcut.register('CommandOrControl+Alt+P', togglePetWindow);

    app.on('before-quit', saveState);
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
      // keep running in the tray
    }
  });

  app.on('activate', () => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.show();
  });

  app.on('will-quit', () => {
    globalShortcut.unregisterAll();
    saveState();
  });
}
