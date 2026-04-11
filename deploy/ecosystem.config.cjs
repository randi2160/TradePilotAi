// PM2 Ecosystem — AutoTrader Pro
// Start:   pm2 start ecosystem.config.cjs
// Monitor: pm2 monit
// Logs:    pm2 logs autotrader-api
// Save:    pm2 save && pm2 startup

module.exports = {
  apps: [
    {
      name:         'autotrader-api',
      cwd:          '/var/www/autotrader/backend',
      script:       'venv/bin/python',
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
      error_file:        '/var/log/autotrader/api-error.log',
      out_file:          '/var/log/autotrader/api-out.log',
      merge_logs:        true,
    },
  ],
}
