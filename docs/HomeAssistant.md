# Configuração do Home Assistant para Integração com o Middleware Middts

Este documento fornece as instruções para configurar o **Home Assistant** via **Docker**, integrando-se ao middleware **Middts** para controle de dispositivos IoT, como luzes e sensores. O cenário foi montado em um computador windows + wsl.

---

## 1. **Instalação do Home Assistant via Docker**

Antes de configurar os dispositivos, é necessário instalar e rodar o **Home Assistant** em um container Docker.

### **Passo 1: Criar um Diretório de Configuração**
```bash
mkdir -p ~/homeassistant
```

### **Passo 2: Executar o Home Assistant no Docker**
```bash
docker run -d \
  --name homeassistant \
  --restart=unless-stopped \
  -e TZ=America/Sao_Paulo \
  -v ~/homeassistant:/config \
  -p 8123:8123 \
  homeassistant/home-assistant:stable
```

Acesse o **Home Assistant** via navegador:
```
http://localhost:8123
```

---

## 2. **Configuração do Arquivo `configuration.yaml`**

A seguir, configuramos comandos REST para ligar/desligar luzes e sensores, garantindo a comunicação com o **middleware Middts**.

### **2.1 Comandos REST para Controle de Luzes**

```yaml
rest_command:
  light1_on:
    url: "http://192.168.1.2:8000/api/orchestrator/systems/1/instances/4/properties/7/"
    method: "put"
    headers:
      Content-Type: "application/json"
    payload: '{"value": true}'

  light1_off:
    url: "http://192.168.1.2:8000/api/orchestrator/systems/1/instances/4/properties/7/"
    method: "put"
    headers:
      Content-Type: "application/json"
    payload: '{"value": false}'

  light2_on:
    url: "http://192.168.1.2:8000/api/orchestrator/systems/1/instances/16/properties/20/"
    method: "put"
    headers:
      Content-Type: "application/json"
    payload: '{"value": true}'

  light2_off:
    url: "http://192.168.1.2:8000/api/orchestrator/systems/1/instances/16/properties/20/"
    method: "put"
    headers:
      Content-Type: "application/json"
    payload: '{"value": false}'
```

### **2.2 Sensores REST para Monitoramento do Estado das Luzes**

```yaml
sensor:
  - platform: rest
    name: "Estado da Luz Quarto 1"
    resource: "http://192.168.1.2:8000/api/orchestrator/systems/1/instances/4/properties/7/value/"
    method: GET
    headers:
      Content-Type: "application/json"
    value_template: "{{ value_json.value }}"
    scan_interval: 1  # Atualiza a cada 1 segundo

  - platform: rest
    name: "Estado da Luz Quarto 2"
    resource: "http://192.168.1.2:8000/api/orchestrator/systems/1/instances/16/properties/20/value/"
    method: GET
    headers:
      Content-Type: "application/json"
    value_template: "{{ value_json.value }}"
    scan_interval: 1  # Atualiza a cada 1 segundo
```

### **2.3 Switch Template para Controle dos Dispositivos**

```yaml
switch:
  - platform: template
    switches:
      luz_quarto_1:
        friendly_name: "Luz Quarto 1"
        value_template: "{{ is_state('sensor.estado_da_luz_quarto_1', 'true') }}"
        turn_on:
          service: rest_command.light1_on
        turn_off:
          service: rest_command.light1_off

      luz_quarto_2:
        friendly_name: "Luz Quarto 2"
        value_template: "{{ is_state('sensor.estado_da_luz_quarto_2', 'true') }}"
        turn_on:
          service: rest_command.light2_on
        turn_off:
          service: rest_command.light2_off
```

---

## 3. **Acelerar a Sincronização com Middts**

Por padrão, o Home Assistant atualiza sensores REST a cada **30 segundos**, mas podemos reduzir esse tempo para **1 segundo** usando `scan_interval` nos sensores REST.

Isso garante que **mudanças físicas no dispositivo sejam detectadas rapidamente**.

Se precisar de um método alternativo, também é possível criar uma **automacao** para forçar a atualização sempre que o switch for alterado:

```yaml
automation:
  - alias: "Atualizar Estado da Luz Quarto 1 Rapidamente"
    trigger:
      - platform: state
        entity_id: switch.luz_quarto_1
    action:
      - service: homeassistant.update_entity
        entity_id: sensor.estado_da_luz_quarto_1
```

---

## 4. **Testando e Depurando**

### **4.1 Reiniciar o Home Assistant**
Para aplicar as configurações, reinicie o Home Assistant:
```bash
docker restart homeassistant
```

### **4.2 Testar os Comandos**
Acesse o **Dashboard do Home Assistant** e tente:
1. **Ligar e desligar as luzes pelos botões.**
2. **Observar se o estado muda automaticamente quando a luz é ligada/desligada manualmente.**

### **4.3 Verificar Logs do Home Assistant**
Se algo não funcionar, verifique os logs:
```bash
docker logs -f homeassistant
```

---
## 5. **Configuração no WSL**
Se estiver rodando no **WSL (Windows Subsystem for Linux)** e o middleware **Middts** estiver rodando no próprio Windows ou em outro container, é necessário apontar corretamente para o IP do host ou do outro container:

### **Opção 1: Apontar para o IP do Host**
No `configuration.yaml`, substitua `localhost` pelo IP do Windows (descubra executando `ipconfig` no Windows):

```yaml
resource: "http://192.168.x.x:8000/api/orchestrator/systems/..."
```

### **Opção 2: Se Middts Estiver em Outro Container**
Certifique-se de que os containers do Home Assistant e do Middts estão na mesma rede Docker:
```bash
docker network create homeassistant_network
docker network connect homeassistant_network homeassistant
docker network connect homeassistant_network middts_container
```
Em seguida, no `configuration.yaml`, use o nome do container Middts:
```yaml
resource: "http://middts_container:8000/api/orchestrator/systems/..."
```

---

## 6. **Conclusão**
Este guia configurou o **Home Assistant** para controlar e monitorar dispositivos através do **middleware Middts** via chamadas **REST API**. Com isso, os dispositivos podem ser acionados tanto pela interface do Home Assistant quanto manualmente, com sincronização rápida.

Se houver dúvidas ou erros, verifique os logs e ajustes na API para garantir compatibilidade com os comandos enviados. 🚀
