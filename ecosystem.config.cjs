// DEPRECATED — the canonical PM2 config is deploy/ecosystem.config.cjs.
// rollout.sh uses that one. This root-level file exists only for
// backwards-compat with anyone who was running `pm2 start
// ecosystem.config.cjs` from the repo root; it now matches the `deploy/`
// version (app name "autotrader-api") so the two can't drift.
//
// Prefer:
//   pm2 start deploy/ecosystem.config.cjs
//   pm2 logs autotrader-api
module.exports = {
  apps: [
    {
      name:        "autotrader-api",
      cwd:         "./backend",
      script:      "./backend/venv/bin/python",
      args:        "main.py",
      interpreter: "none",
      env: { PORT: 8000 },
    },
  ],
}
