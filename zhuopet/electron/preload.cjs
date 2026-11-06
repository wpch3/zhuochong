const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('zhuopet', {
  platform: process.platform,
  quit: () => ipcRenderer.send('pet:quit'),
  setIgnoreMouseEvents: (value) => ipcRenderer.send('pet:ignore', Boolean(value)),
  setAlwaysOnTop: (value) => ipcRenderer.send('pet:always-on-top', Boolean(value)),
  minimize: () => ipcRenderer.send('pet:minimize'),
  togglePetWindow: () => ipcRenderer.send('pet:toggle-pet'),
  openChat: () => ipcRenderer.send('pet:open-chat'),
  openSettings: () => ipcRenderer.send('pet:open-settings'),
  onOpenChat: (callback) => {
    const handler = () => callback();
    ipcRenderer.on('pet:open-chat', handler);
    return () => ipcRenderer.removeListener('pet:open-chat', handler);
  },
  onOpenSettings: (callback) => {
    const handler = () => callback();
    ipcRenderer.on('pet:open-settings', handler);
    return () => ipcRenderer.removeListener('pet:open-settings', handler);
  },
  onOpenStudio: (callback) => {
    const handler = () => callback();
    ipcRenderer.on('pet:open-studio', handler);
    return () => ipcRenderer.removeListener('pet:open-studio', handler);
  },
  onClickThrough: (callback) => {
    const handler = (_event, value) => callback(Boolean(value));
    ipcRenderer.on('pet:click-through', handler);
    return () => ipcRenderer.removeListener('pet:click-through', handler);
  },
});
