/**
 * Vite plugin: ensure the Error Analysis API is listening on :8010 while
 * ``npm run dev`` runs, so /api proxy calls do not return Bad Gateway.
 */
import { spawn, type ChildProcess } from 'node:child_process'
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Plugin } from 'vite'

const API_HEALTH = 'http://127.0.0.1:8010/api/health'
const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function probeApi(timeoutMs = 800): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(API_HEALTH, (res) => {
      res.resume()
      resolve(typeof res.statusCode === 'number' && res.statusCode < 500)
    })
    req.on('error', () => resolve(false))
    req.setTimeout(timeoutMs, () => {
      req.destroy()
      resolve(false)
    })
  })
}

function resolveApiCommand(): { command: string; args: string[]; cwd: string } | null {
  const winExe = path.join(PROJECT_ROOT, '.venv', 'Scripts', 'error-analysis-api.exe')
  const unixBin = path.join(PROJECT_ROOT, '.venv', 'bin', 'error-analysis-api')
  const winPy = path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe')
  const unixPy = path.join(PROJECT_ROOT, '.venv', 'bin', 'python')

  if (process.platform === 'win32' && fs.existsSync(winExe)) {
    return { command: winExe, args: [], cwd: PROJECT_ROOT }
  }
  if (fs.existsSync(unixBin)) {
    return { command: unixBin, args: [], cwd: PROJECT_ROOT }
  }
  if (process.platform === 'win32' && fs.existsSync(winPy)) {
    return {
      command: winPy,
      args: ['-c', 'from error_analysis.api import main; main()'],
      cwd: PROJECT_ROOT,
    }
  }
  if (fs.existsSync(unixPy)) {
    return {
      command: unixPy,
      args: ['-c', 'from error_analysis.api import main; main()'],
      cwd: PROJECT_ROOT,
    }
  }
  return null
}

async function waitForApi(attempts = 40, delayMs = 250): Promise<boolean> {
  for (let i = 0; i < attempts; i += 1) {
    if (await probeApi()) return true
    await new Promise((r) => setTimeout(r, delayMs))
  }
  return false
}

export function startApiPlugin(): Plugin {
  let child: ChildProcess | null = null
  let startedByPlugin = false

  return {
    name: 'error-analysis-start-api',
    apply: 'serve',
    async configureServer(server) {
      if (process.env.ERROR_ANALYSIS_SKIP_API_AUTOSTART === '1') {
        return
      }

      if (await probeApi()) {
        server.config.logger.info('Error Analysis API already running on http://127.0.0.1:8010')
        return
      }

      const cmd = resolveApiCommand()
      if (!cmd) {
        server.config.logger.warn(
          'Error Analysis API is not running on :8010 and .venv was not found.\n' +
            '  From the repo root run:  python -m venv .venv && pip install -e ".[web]"\n' +
            '  Then start the API:     error-analysis-api\n' +
            '  Or use VS Code task:    "Error Analysis: API + UI"',
        )
        return
      }

      server.config.logger.info('Starting Error Analysis API on http://127.0.0.1:8010 …')
      child = spawn(cmd.command, cmd.args, {
        cwd: cmd.cwd,
        env: {
          ...process.env,
          ERROR_ANALYSIS_RELOAD: process.env.ERROR_ANALYSIS_RELOAD || '1',
        },
        stdio: 'inherit',
        windowsHide: true,
      })
      startedByPlugin = true

      child.on('exit', (code, signal) => {
        if (startedByPlugin) {
          server.config.logger.warn(
            `Error Analysis API exited (code=${code ?? 'null'}, signal=${signal ?? 'null'})`,
          )
        }
        child = null
        startedByPlugin = false
      })

      const ready = await waitForApi()
      if (!ready) {
        server.config.logger.error(
          'Timed out waiting for Error Analysis API on http://127.0.0.1:8010.\n' +
            '  Check .env / Datadog credentials and run error-analysis-api manually.',
        )
      } else {
        server.config.logger.info('Error Analysis API is ready (proxied via /api)')
      }

      const stop = () => {
        if (child && startedByPlugin && !child.killed) {
          startedByPlugin = false
          child.kill('SIGTERM')
          child = null
        }
      }
      process.once('exit', stop)
      process.once('SIGINT', stop)
      process.once('SIGTERM', stop)
      server.httpServer?.once('close', stop)
    },
  }
}
