import os
import subprocess
import sys

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "middleware_dt.settings")
    
    # Inicia o listener do gateway
    listener_process = subprocess.Popen([sys.executable, "manage.py", "listen_gateway"])
    
    # Inicia o verificador de status dos devices
    status_checker_process = subprocess.Popen([sys.executable, "manage.py", "check_device_status", "--interval", "2"])
    
    runserver_process = subprocess.Popen([sys.executable, "manage.py", "runserver", "0.0.0.0:8000",])
    
    try:
        # Aguarda os processos terminarem (que só acontece se houver erro)
        listener_process.wait()
        status_checker_process.wait()
        runserver_process.wait()
    except KeyboardInterrupt:
        print("Stopping all processes...")
        listener_process.terminate()
        status_checker_process.terminate()
        runserver_process.terminate()
        listener_process.wait()
        status_checker_process.wait()
        runserver_process.wait()

if __name__ == "__main__":
    main()