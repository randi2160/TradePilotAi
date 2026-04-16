// PM2 Ecosystem — AutoTrader Pro
// Start:   pm2 start deploy/ecosystem.config.cjs
// Monitor: pm2 monit
// Logs:    pm2 logs autotrader-api
// Save:    pm2 save && pm2 startup
//
// Paths are resolved relative to THIS file, so the config works from any repo
// location (Lightsail ~/TradePilotAi, AWS /var/www/autotrader, etc.) without
// editing. Logs go to backend/logs/ inside the repo — no sudo needed.

const path    = require('path');
const repoRoot = path.resolve(__dirname, '..');
const backend  = path.join(repoRoot, 'backend');
const logDir   = path.join(backend, 'logs');

module.exports = {
  apps: [
    {
      name:         'autotrader-api',
      cwd:          backend,
      script:       path.join(backend, 'venv', 'bin', 'python'),
      args:         'main.py',
      interpreter:  'none',
      instances:    1,
      autorestart:  true,
      watch:        false,
      max_memory_restart: '512M',
      restart_delay: 5000,
      env: {
        NODE_ENV: 'production',
      },
      log_date_format:   'YYYY-MM-DD HH:mm:ss',
      error_file:        path.join(logDir, 'api-error.log'),
      out_file:          path.join(logDir, 'api-out.log'),
      merge_logs:        true,
    },
  ],
}
