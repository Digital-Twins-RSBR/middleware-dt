# 📊 Relatórios ODTE - InfluxDB Queries

Esta pasta contém os relatórios InfluxDB para análise de latência ODTE (One-Way Delay Time) bidirectional no sistema URLLC.

## 📋 Relatórios Disponíveis

### 1. **Análises por Direção**

#### `latencia_s2m_otimizada.influx`
- **Propósito:** Análise detalhada S2M (Simulator → Middleware)
- **Dados:** Telemetria de sensores para middleware
- **Measurement:** `device_data` 
- **Sources:** `simulator` (sent) → `middts` (received)
- **Métricas:** Latência média, P95, por sensor e global

#### `latencia_m2s_otimizada.influx`
- **Propósito:** Análise detalhada M2S (Middleware → Simulator)
- **Dados:** RPCs de comando do middleware para simuladores
- **Measurement:** `latency_measurement`
- **Sources:** `middts` (sent) → `simulator` (received)
- **Métricas:** Latência média, P95, por sensor e global

### 2. **Visualizações Combinadas**

#### `latencia_odte_scatter_combined.influx`
- **Propósito:** Scatter plot bidirectional S2M + M2S
- **Visualização:** Pontos de dispersão com direções diferenciadas
- **Uso:** Comparação direta das latências por direção
- **Output:** `latencia_odte_scatter_combined`, `latencia_comparison_stats`

#### `latencia_odte_timeline.influx`
- **Propósito:** Evolução temporal das latências
- **Visualização:** Série temporal com múltiplas agregações
- **Outputs:**
  - `latencia_timeline_raw` - Dados brutos
  - `latencia_timeline_1min_avg` - Média por minuto
  - `latencia_timeline_moving_avg` - Média móvel 5min
  - `latencia_timeline_p95` - P95 por minuto
  - `urllc_compliance_timeline` - Compliance <1ms

#### `latencia_odte_histogram_comparison.influx`
- **Propósito:** Distribuição estatística das latências
- **Visualização:** Histogramas comparativos S2M vs M2S
- **Bins:** 0-10ms, 10-20ms, ..., até 1000ms
- **Outputs:**
  - `latencia_distribution_comparison` - Histograma combinado
  - `latencia_percentiles_comparison` - P50, P95, P99 por direção

### 3. **Dashboard Executivo**

#### `latencia_odte_urllc_dashboard.influx`
- **Propósito:** Métricas executivas de conformidade URLLC
- **Targets:** <1ms, <5ms, <10ms compliance rates
- **Outputs:**
  - `urllc_compliance_1ms_global` - Taxa global <1ms
  - `urllc_compliance_1ms_by_direction` - Compliance por direção
  - `urllc_compliance_1ms_by_sensor` - Compliance por sensor
  - `urllc_latency_categories` - Categorização de performance
  - `urllc_sla_violations` - Violações >10ms
  - `urllc_performance_summary` - Resumo estatístico

## 🎨 Como Usar no Grafana

### 1. **Scatter Plot**
```
Panel Type: Scatter
Query: latencia_odte_scatter_combined.influx
X-Axis: _time
Y-Axis: latencia_ms
Series: direction (S2M/M2S)
```

### 2. **Timeline**
```
Panel Type: Time Series
Query: latencia_odte_timeline.influx
Multiple Series:
- latencia_timeline_raw
- latencia_timeline_moving_avg
- latencia_timeline_p95
```

### 3. **Histograma**
```
Panel Type: Bar Chart
Query: latencia_odte_histogram_comparison.influx
X-Axis: le (bins)
Y-Axis: _value (count)
Group By: direction
```

### 4. **Dashboard URLLC**
```
Panel Types: Stat + Bar Chart + Table
Queries: latencia_odte_urllc_dashboard.influx
- Compliance rates como Stat panels
- Categories como Bar chart
- Performance summary como Table
```

## 🔧 Configuração InfluxDB

### Variáveis de Template (Grafana)
```
timeRangeStart: $__timeFrom
timeRangeStop: $__timeTo
```

### Bucket e Organização
```
Bucket: iot_data
Organization: middts
```

### Estrutura de Dados

#### S2M (device_data)
```
measurement: device_data
tags: sensor, source
fields: sent_timestamp, received_timestamp, [sensor_data]
```

#### M2S (latency_measurement)  
```
measurement: latency_measurement
tags: sensor, source
fields: sent_timestamp, received_timestamp
```

## 📊 Métricas Chave

### Targets URLLC
- **Excellent:** <1ms (target principal)
- **Good:** <5ms (aceitável)
- **Acceptable:** <10ms (limite SLA)
- **High Latency:** >10ms (violação)

### Filtros Aplicados
- **Range:** 0ms ≤ latência < 1000ms
- **Correlation Window:** 30s para evitar falsos positivos
- **Deduplication:** min() por evento para evitar duplicatas

## 🚀 Execução

### Via InfluxDB CLI
```bash
influx query --org middts --file latencia_s2m_otimizada.influx
```

### Via HTTP API
```bash
curl -X POST 'http://localhost:8086/api/v2/query?org=middts' \
  -H 'Authorization: Token YOUR_TOKEN' \
  -H 'Content-Type: application/vnd.flux' \
  --data-binary @latencia_s2m_otimizada.influx
```

### Via Grafana
- Import query como Data Source
- Configure time range variables
- Aplique visualizações apropriadas

---

**Status:** ✅ Funcionais - Dados ODTE reais sendo capturados  
**Última Atualização:** Setembro 2025