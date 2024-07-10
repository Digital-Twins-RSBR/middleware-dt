from concurrent.futures import ThreadPoolExecutor, as_completed

class ThreadManager:
    def __init__(self, max_workers):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.futures = []

    def add_task(self, task, *args):
        future = self.executor.submit(task, *args)
        self.futures.append(future)

    def stop_all(self):
        self.executor.shutdown(wait=True)

'''
Exemplo de Uso

 max_workers = 10  # Define o número máximo de threads no pool -Avaliar essa questão
manager = ThreadsManager(max_workers=max_workers)

Em algum local eu preciso fazer o seguinte procedimento:

manager.add_task(digitalTwinInstancePropertyObject.periodic_call,5) # 5 é o tempo em segundos de leitura

Precisa adotar algum mecanismos de escalabilidade e avaliar as possibilidades disso, inclusive lançando mão de estatégias do docker, kubernetes ou outra estratégia

'''