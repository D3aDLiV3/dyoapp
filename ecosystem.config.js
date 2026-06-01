module.exports = {
  apps: [
    {
      name: "wooposadmin",
      script: "/usr/projects/dyoapp/dyoapp/.venv/bin/streamlit",
      args: "run app_web.py --server.port 8501 --server.address 0.0.0.0",
      cwd: "/usr/projects/dyoapp/dyoapp",
      interpreter: "none"
    }
  ]
}
