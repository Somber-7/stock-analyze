const { app, BrowserWindow, ipcMain, dialog, Notification, shell } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')
const http = require('http')

let mainWindow = null
let backendProcess = null
let port = 0
let quitting = false
const deliveredAlerts = new Set()

function startBackend() {
  if (backendProcess) return Promise.resolve()
  return new Promise((resolve, reject) => {
    const packaged = app.isPackaged
    const executable = packaged
      ? path.join(process.resourcesPath, 'backend.exe')
      : process.env.STOCK_PYTHON || path.join(app.getPath('home'), 'miniconda3', 'envs', 'stock-analyze', 'python.exe')
    const cwd = packaged ? process.resourcesPath : path.join(__dirname, '..', '..')
    const child = spawn(executable, packaged ? [] : [path.join(cwd, 'run.py')], {
      cwd, windowsHide: true,
      env: { ...process.env, STOCK_PORT: String(port), PYTHONIOENCODING: 'utf-8',
        ...(packaged ? { STOCK_BASE_DIR: app.getPath('userData') } : {}) },
    })
    backendProcess = child
    let output = ''
    const timer = setTimeout(() => reject(new Error('백엔드 실행 시간이 초과되었습니다.')), 90000)
    child.stdout?.on('data', chunk => {
      output = (output + chunk.toString()).slice(-8192)
      const match = output.match(/(?:^|\n)STOCK_PORT=(\d+)\r?\n/)
      if (match) {
        port = Number(match[1])
        clearTimeout(timer)
        resolve()
      }
    })
    child.stderr?.on('data', chunk => console.error('[backend]', chunk.toString()))
    child.on('error', () => {
      clearTimeout(timer)
      if (backendProcess === child) backendProcess = null
      reject(new Error('백엔드 실행 파일을 찾을 수 없습니다.'))
    })
    child.on('exit', () => {
      clearTimeout(timer)
      if (backendProcess === child) backendProcess = null
      reject(new Error('백엔드가 종료되었습니다. 다시 실행해주세요.'))
    })
  })
}

async function stopBackend() {
  const child = backendProcess
  if (!child) return
  if (process.platform === 'win32' && child.pid) {
    // PyInstaller onefile runs a child process: terminate our whole tree.
    await new Promise(resolve => {
      const killer = spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true })
      killer.on('error', resolve)
      killer.on('exit', resolve)
    })
  } else {
    child.kill()
  }
  if (backendProcess === child) backendProcess = null
}

async function waitForBackend() {
  const deadline = Date.now() + 30000
  while (Date.now() < deadline) {
    if (!backendProcess) throw new Error('백엔드가 종료되었습니다.')
    const ready = await new Promise(resolve => {
      const request = http.get(`http://127.0.0.1:${port}/api/health`, res => {
        let body = ''
        res.on('data', chunk => { body += chunk })
        res.on('end', () => {
          try { resolve(res.statusCode === 200 && JSON.parse(body).broker === 'namuh') }
          catch { resolve(false) }
        })
        res.on('error', () => resolve(false))
      })
      request.setTimeout(1000, () => { request.destroy(); resolve(false) })
      request.on('error', () => resolve(false))
    })
    if (ready) return
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  throw new Error('백엔드 응답 시간이 초과되었습니다.')
}

async function ensureCredentials() {
  if (!app.isPackaged) return true
  const directory = app.getPath('userData')
  const destination = path.join(directory, 'Api_Key.txt')
  if (fs.existsSync(destination) || fs.existsSync(path.join(directory, '.env')) ||
      (process.env.NAMUH_APP_KEY && process.env.NAMUH_APP_SECRET)) return true
  const selection = await dialog.showOpenDialog({
    title: '나무증권 API 키 파일 선택',
    message: '발급받은 APP Key와 APP Secret이 저장된 Api_Key.txt를 선택해주세요.',
    properties: ['openFile'], filters: [{ name: 'API 키 텍스트 파일', extensions: ['txt'] }],
  })
  if (selection.canceled) return false
  fs.mkdirSync(directory, { recursive: true })
  fs.copyFileSync(selection.filePaths[0], destination)
  return true
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280, height: 800, minWidth: 900, minHeight: 600,
    title: 'Stock Analyze · 나무증권', autoHideMenuBar: true,
    // Windows draws the caption buttons over the in-app workspace bar (71px + 1px border).
    titleBarStyle: 'hidden',
    titleBarOverlay: { color: '#111619', symbolColor: '#9aa9ae', height: 71 },
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true },
  })
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const target = new URL(url)
      if (['https:', 'http:'].includes(target.protocol) && !target.username && !target.password) {
        shell.openExternal(target.href).catch(() => {})
      }
    } catch { /* Ignore malformed links. */ }
    return { action: 'deny' }
  })
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (new URL(url).origin !== `http://127.0.0.1:${port}`) event.preventDefault()
  })
  mainWindow.loadURL(`http://127.0.0.1:${port}`)
  mainWindow.on('closed', () => { mainWindow = null })
}

ipcMain.handle('backend:status', () => !!backendProcess)
ipcMain.handle('watch:notify', (event, rows) => {
  if (!mainWindow || event.sender !== mainWindow.webContents ||
      new URL(event.senderFrame.url).origin !== `http://127.0.0.1:${port}` || !Array.isArray(rows)) return false
  const fresh = rows.slice(0, 1000).filter(row => row && typeof row.id === 'string' && row.id.length <= 100 &&
    typeof row.name === 'string' && row.name.length <= 100 && /^[0-9A-Z]{6}$/.test(row.code) &&
    Number.isSafeInteger(row.price) && row.price > 0 && !deliveredAlerts.has(row.id))
  if (!fresh.length || !Notification.isSupported()) return false
  const first = fresh[0]
  const notification = new Notification({ title: `Stock Analyze · 가격 알림 ${fresh.length}건`,
    body: `${first.name} (${first.code}) ${first.price.toLocaleString('ko-KR')}원 · 조건 도달${fresh.length > 1 ? ` 외 ${fresh.length - 1}건` : ''}` })
  notification.on('click', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.show(); mainWindow.focus(); mainWindow.webContents.send('watch:open')
  })
  notification.on('failed', () => { /* In-app notification and history remain available. */ })
  notification.show()
  fresh.forEach(row => deliveredAlerts.add(row.id))
  return true
})
ipcMain.handle('backend:stop', async () => { await stopBackend(); return true })
ipcMain.handle('backend:start', async () => {
  try { await startBackend(); await waitForBackend(); return true }
  catch (error) { await stopBackend(); throw error }
})

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus() }
  })
  app.whenReady().then(async () => {
    app.setAppUserModelId('com.stock-analyze.app')
    try {
      if (!await ensureCredentials()) { app.quit(); return }
      await startBackend()
      await waitForBackend()
      createWindow()
    } catch (error) {
      dialog.showErrorBox('Stock Analyze 실행 실패', error.message)
      app.quit()
    }
  })
}
app.on('window-all-closed', () => app.quit())
app.on('before-quit', event => {
  if (!quitting && backendProcess) {
    event.preventDefault()
    quitting = true
    stopBackend().finally(() => app.quit())
  }
})
