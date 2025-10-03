#!/bin/bash

# Script para gerar dados M2S enviando RPCs de teste
# Executa chamadas update_causal_property para ativar o fluxo M2S

echo "🔄 Iniciando geração de dados M2S..."

# Verificar se o middleware está rodando
if ! curl -s http://localhost:8000/api/ > /dev/null 2>&1; then
    echo "❌ Middleware não está acessível em localhost:8000"
    exit 1
fi

echo "✅ Middleware acessível"

# Listar devices para encontrar IDs válidos
echo "📋 Buscando devices disponíveis..."
DEVICES=$(curl -s "http://localhost:8086/api/v2/query?org=middts&bucket=iot_data" \
  -H "Authorization: Token SMftV4PQPM61kjJlyie67VZvwgKQdPiVo2kFgEcMHTBjFVUtLKaNhPR8MTp102enU-d3rnCN8qz_GLOiYTZEjw==" \
  -H "Content-Type: application/vnd.flux" \
  -d 'from(bucket: "iot_data") |> range(start: -1h) |> filter(fn: (r) => r._measurement == "device_data" and r.source == "simulator") |> keep(columns: ["sensor"]) |> unique(column: "sensor") |> limit(n: 5)' \
  | grep -o 'a[0-9a-f\-]*' | head -5)

echo "🎯 Devices encontrados:"
echo "$DEVICES"

# Para cada device, tentar encontrar o endpoint correto
echo "🚀 Enviando RPCs de teste..."

for device in $DEVICES; do
    echo "📡 Testando device: $device"
    
    # Tentar diferentes endpoints possíveis
    for system_id in 1 2; do
        for instance_id in 1 2 3 4 5; do
            for property_id in 1 2 3; do
                response=$(curl -s -w "%{http_code}" -o /dev/null \
                    -X PUT "http://localhost:8000/api/orchestrator/systems/$system_id/instances/$instance_id/properties/$property_id/" \
                    -H "Content-Type: application/json" \
                    -d '{"value": true}')
                
                if [ "$response" = "200" ] || [ "$response" = "201" ]; then
                    echo "✅ RPC enviado: system=$system_id, instance=$instance_id, property=$property_id"
                    sleep 1
                fi
            done
        done
    done
done

echo "⏱️  Aguardando 5 segundos para timestamps serem capturados..."
sleep 5

echo "📊 Verificando dados M2S gerados..."
curl -s "http://localhost:8086/api/v2/query?org=middts&bucket=iot_data" \
  -H "Authorization: Token SMftV4PQPM61kjJlyie67VZvwgKQdPiVo2kFgEcMHTBjFVUtLKaNhPR8MTp102enU-d3rnCN8qz_GLOiYTZEjw==" \
  -H "Content-Type: application/vnd.flux" \
  -d 'from(bucket: "iot_data") |> range(start: -2m) |> filter(fn: (r) => r._measurement == "latency_measurement" and r.source == "simulator") |> count()' \
  | grep -E "_value|simulator"

echo "🎉 Script concluído!"