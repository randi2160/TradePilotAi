
module.exports = {

  apps: [

    {

      name: "tradepilot-backend",

      cwd: "./backend",

      script: "./venv/bin/python",

      args: "main.py",

      interpreter: "none",

      env: { PORT: 8000 }

    }

  ]

}

