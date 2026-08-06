# Guia de Configuração do Histograma ODTE no InfluxDB/Grafana

## 🎯 Objetivo
Configurar visualização de histogramars comparativos das latências S2M vs M2S para análise URLLC.

## 📊 Métodos de Configuração

### **Método 1: InfluxDB Data Explorer**

1. **Acesse o InfluxDB UI:**
   ```
   http://localhost:8086
   ```

2. **Navegue para Data Explorer:**
   - Clique em "Data Explorer" no menu lateral
   - Selecione o bucket: `iot_data`

3. **Cole a Query Flux:**
   - Copie todo o conteúdo do arquivo `latencia_odte_histogram_comparison.influx`
   - Cole na área de query do Data Explorer

4. **Configure Time Range:**
   - Selecione o período desejado (ex: Last 1h, Last 24h)
   - Para dados históricos: Custom range

5. **Execute e Visualize:**
   - Clique em "Submit" para executar
   - Escolha visualização "Histogram" ou "Table"

### **Método 2: Grafana Dashboard (Recomendado)**

#### **Passo 1: Configurar Data Source**
1. Acesse Grafana: `http://localhost:3000`
2. Vá em Configuration > Data Sources
3. Add InfluxDB data source:
   ```
   URL: http://localhost:8086
   Database: iot_data
   Query Language: Flux
   Organization: your-org
   Token: your-influx-token
   ```

#### **Passo 2: Importar Dashboard**
1. Vá em "+" > Import
2. Cole o JSON do arquivo `grafana_histogram_dashboard.json`
3. Configure data source UID
4. Salve o dashboard

#### **Passo 3: Configuração de Painéis**

**Panel 1: Histograma Comparativo**
- **Type:** Histogram
- **Query:** Use a parte `latencia_distribution_comparison` da query
- **Visualization:** 
  - X-axis: Latency bins (0-1000ms)
  - Y-axis: Count
  - Series: S2M vs M2S

**Panel 2: Percentis**
- **Type:** Stat/Table
- **Query:** Use a parte `latencia_percentiles_comparison` da query
- **Display:** P50, P95, P99 para ambas direções

## 🔧 Configurações Avançadas

### **Bins do Histograma:**
```flux
bins: [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 150.0, 200.0, 300.0, 500.0, 1000.0]
```

### **Filtros de Qualidade:**
- Latência válida: 0ms ≤ latência < 1000ms
- Time diff válido: 0ns ≤ diff < 30s
- Existência de timestamps: `exists sent_timestamp and exists received_timestamp`

### **Agrupamento:**
- Por sensor para evitar duplicatas
- Minimum latência por grupo (deduplicação)

## 📈 Interpretação dos Resultados

### **Histograma:**
- **Picos baixos (0-50ms):** Latências URLLC ideais
- **Cauda longa (>100ms):** Possíveis outliers ou problemas de rede
- **Comparação S2M vs M2S:** Identificar assimetrias

### **Percentis:**
- **P50 (Mediana):** Latência típica
- **P95:** SLA de 95% dos casos
- **P99:** Casos extremos, importante para URLLC

## 🚀 Exemplo de Uso

### **Query Simplificada para Teste:**
```flux
from(bucket: "iot_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "device_data")
  |> filter(fn: (r) => r._field == "sent_timestamp" or r._field == "received_timestamp")
  |> group(columns: ["sensor", "source"])
  |> count()
```

### **Verificação de Dados:**
```flux
// Verificar dados S2M
from(bucket: "iot_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "device_data")
  |> group(columns: ["source", "_field"])
  |> count()

// Verificar dados M2S  
from(bucket: "iot_data")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "latency_measurement")
  |> group(columns: ["source", "_field"])
  |> count()
```

## 🔍 Troubleshooting

### **Problema: "No data"**
- Verificar se dados existem no período selecionado
- Confirmar nomes corretos de measurements e fields
- Verificar conectividade InfluxDB

### **Problema: "Query timeout"**
- Reduzir time range
- Adicionar mais filtros
- Otimizar query com sampling

### **Problema: "Empty histogram"**
- Verificar se join está funcionando
- Confirmar existência de timestamps
- Verificar filtros de validação

## 📝 Notas Importantes

1. **Performance:** Query complexa, use time ranges menores para desenvolvimento
2. **Dados:** Certifique-se que tanto S2M quanto M2S estão gerando dados
3. **URLLC:** Foque em latências < 50ms para análise URLLC
4. **Alertas:** Configure alertas para P95 > 50ms ou P99 > 100ms