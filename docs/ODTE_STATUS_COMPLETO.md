# Status ODTE (One-Way Delay Time) - Timestamps Completos

## Situação Atual: IMPLEMENTAÇÃO COMPLETA ✅

### Timestamps Implementados:

#### S2M (Simulator → Middleware):
- ✅ **sent_timestamp**: Simulador captura quando envia telemetria (`send_telemetry_async`)
- ✅ **received_timestamp**: Middleware captura quando recebe via REST API (`update_causal_property`)
- ✅ **Estrutura**: `device_data` measurement com source="simulator" e source="middleware"

#### M2S (Middleware → Simulator):
- ✅ **sent_timestamp**: Middleware captura quando envia RPC (`_write_m2s_sent_timestamp`)
- ✅ **received_timestamp**: Simulador captura quando recebe RPC (`on_message`)
- ✅ **Estrutura**: `latency_measurement` measurement com direction="M2S"

### Cálculo ODTE Real:

#### S2M Real Latency:
```
ODTE_S2M = received_timestamp_middleware - sent_timestamp_simulator
```

#### M2S Real Latency:
```
ODTE_M2S = received_timestamp_simulator - sent_timestamp_middleware
```

### Flux Reports Disponíveis:

1. **`latencia_odte_s2m_real.influx`**: Latência S2M usando timestamps exatos
2. **`latencia_odte_m2s_real.influx`**: Latência M2S usando timestamps exatos
3. **`latencia_odte_scatter_combined.influx`**: Scatter plot combinado S2M + M2S

### Estrutura de Dados:

#### device_data (S2M):
```
device_data,sensor=<sensor_tag>,source=simulator sent_timestamp=<ts> <ts>
device_data,sensor=<sensor_tag>,source=middleware received_timestamp=<ts> <ts>
```

#### latency_measurement (M2S):
```
latency_measurement,sensor=<sensor_tag>,direction=M2S sent_timestamp=<ts> <ts>
latency_measurement,sensor=<sensor_tag>,direction=M2S received_timestamp=<ts> <ts>
```

### Vantagens da Implementação:

1. **Precisão**: Timestamps capturados exatamente no momento de envio/recebimento
2. **ODTE Real**: Cálculo one-way delay verdadeiro, não round-trip
3. **Correlação**: Algoritmo de matching temporal para associar eventos
4. **Visualização**: Scatter plots separados e combinados para análise completa
5. **Performance**: Dados diretos do InfluxDB sem aproximações

### Próximos Passos:

1. Reiniciar topologia para aplicar as mudanças
2. Executar cenário para gerar dados com timestamps completos
3. Usar os novos Flux reports para visualização ODTE real
4. Verificar latências < 1ms conforme especificação URLLC

### Arquivos Modificados:

- `services/iot_simulator/devices/management/commands/send_telemetry.py`: Timestamps completos no simulador
- `services/middleware-dt/facade/models.py`: M2S sent_timestamp (já implementado)
- `services/middleware-dt/core/property_observer.py`: S2M received_timestamp (já implementado)

### Comandos para Testar:

```bash
# Reiniciar topologia
make restart

# Verificar dados S2M
curl -s "http://localhost:8086/api/v2/query?org=condominio&bucket=condominio" \
  -H "Authorization: Token admin_token" \
  -H "Content-Type: application/vnd.flux" \
  -d 'from(bucket: "condominio") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "device_data" and (r.source == "simulator" or r.source == "middleware"))'

# Verificar dados M2S
curl -s "http://localhost:8086/api/v2/query?org=condominio&bucket=condominio" \
  -H "Authorization: Token admin_token" \
  -H "Content-Type: application/vnd.flux" \
  -d 'from(bucket: "condominio") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "latency_measurement" and r.direction == "M2S")'
```

## Status: PRONTO PARA MEDIÇÃO ODTE REAL ✅