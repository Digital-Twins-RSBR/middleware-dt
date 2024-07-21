from orchestrator.models import DigitalTwinInstanceProperty
from facade.threadmanager import ThreadsManager
from django.conf import settings
import os
import sys

def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "middleware-dt.settings")
    max_workers = 1  # Define o número máximo de threads no pool -Avaliar essa questão
    manager = ThreadsManager(max_workers=max_workers)
    lightbulb = DigitalTwinInstanceProperty.objects.filter(pk=4).first()
    manager.add_task(lightbulb.periodic_call,5)

if __name__ == '__main__':
    main()