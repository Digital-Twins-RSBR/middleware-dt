
from orchestrator.models import DigitalTwinInstanceProperty


def __main__():
    max_workers = 10  # Define o número máximo de threads no pool -Avaliar essa questão
    manager = ThreadsManager(max_workers=max_workers)

    #Em algum local eu preciso fazer o seguinte procedimento:

    manager.add_task(DigitalTwinInstanceProperty.periodic_call,5)