const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  notifyPriceAlerts: rows => ipcRenderer.invoke('watch:notify', rows),
  onWatchOpen: callback => {
    const handler = () => callback()
    ipcRenderer.on('watch:open', handler)
    return () => ipcRenderer.removeListener('watch:open', handler)
  },
  getStatus: () => ipcRenderer.invoke('backend:status'),
  stopBackend: () => ipcRenderer.invoke('backend:stop'),
  startBackend: () => ipcRenderer.invoke('backend:start'),
})
