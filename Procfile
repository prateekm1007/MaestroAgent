# Procfile for Railway deployment
# Uses the patched API entry point that fixes the commitment classifier

web: cd download/MaestroAgent/maestro-personal && uvicorn maestro_personal_shell.api_patched:app --host 0.0.0.0 --port $PORT
