module.exports = {
  apps: [
    {
      name: "wooposadmin",
      interpreter: "/opt/wooposadmin/.venv/bin/python",
      script: "/opt/wooposadmin/.venv/bin/streamlit",
      args: "run app_web.py",
      cwd: "/opt/wooposadmin",
      autorestart: true,
      watch: false,
      max_memory_restart: "700M",
      env: {
        STREAMLIT_SERVER_HEADLESS: "true",
        STREAMLIT_SERVER_PORT: "8501",
        STREAMLIT_SERVER_ADDRESS: "127.0.0.1",
        TZ: "America/Bogota",
      },
      error_file: "/var/log/wooposadmin/error.log",
      out_file: "/var/log/wooposadmin/out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
    },
  ],
};
