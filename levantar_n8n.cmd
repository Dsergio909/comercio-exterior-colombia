@echo off
rem Levanta el servidor del pipeline (5688) y n8n (5678) en este PC, sin Docker.
rem Uso: doble clic, o desde la terminal: levantar_n8n.cmd
rem Para apagar: cerrar las dos ventanas que se abren.
rem Requisitos: .venv con requirements.txt y n8n instalado en .n8n-app
rem   (npm install --prefix .n8n-app n8n@2.44.7).

cd /d "%~dp0"

rem Puertos de este proyecto: n8n 5678, su "Task Broker" 5698, pipeline 5688.
rem (5679 es del proyecto del taller 3D: no usar.)
set N8N_PORT=5678
set N8N_RUNNERS_BROKER_PORT=5698
set N8N_LISTEN_ADDRESS=127.0.0.1
set N8N_HOST=localhost
set N8N_USER_FOLDER=%~dp0.n8n-datos
set N8N_DIAGNOSTICS_ENABLED=false
set N8N_PERSONALIZATION_ENABLED=false
set N8N_SECURE_COOKIE=false
set N8N_VERSION_NOTIFICATIONS_ENABLED=false
set N8N_BLOCK_ENV_ACCESS_IN_NODE=false
set GENERIC_TIMEZONE=America/Bogota
set PIPELINE_URL=http://127.0.0.1:5688
set OLLAMA_URL=http://127.0.0.1:11434
set OLLAMA_MODELO=qwen3.5:9b
set N8N_URL_PROPIA=http://127.0.0.1:5678

start "Pipeline (5688)" cmd /k ".venv\Scripts\python.exe scripts\servidor.py"
start "n8n (5678)" cmd /k ".n8n-app\node_modules\.bin\n8n.cmd start"

echo.
echo Listo. En unos segundos:
echo   n8n:      http://localhost:5678
echo   pipeline: http://127.0.0.1:5688/salud
echo   Pedir el resumen del ultimo mes:  curl -X POST http://127.0.0.1:5678/webhook/ce-resumen
echo   Ver corridas y el enlace para aprobar: http://127.0.0.1:5688/corridas?n=5
