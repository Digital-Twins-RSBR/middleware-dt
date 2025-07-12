#!/bin/bash

echo "🔍 Verificando serviços obrigatórios do MidDiTS..."

# PostgreSQL
echo -n "PostgreSQL: "
docker exec middleware-dt-db-1 pg_isready -U $POSTGRES_USER > /dev/null 2>&1 && echo "OK" || echo "FALHOU"

# Neo4j
echo -n "Neo4j: "
docker exec middleware-dt-neo4j-1 cypher-shell -u neo4j -p password 'RETURN 1' > /dev/null 2>&1 && echo "OK" || echo "FALHOU"

# InfluxDB
echo -n "InfluxDB: "
curl -s http://localhost:8086/health | grep '"status":"pass"' > /dev/null 2>&1 && echo "OK" || echo "FALHOU"

# Parser
echo -n "Parser API: "
curl -s http://localhost:8080/ | grep -i 'html' > /dev/null 2>&1 && echo "OK" || echo "FALHOU"

echo "✅ Verificação concluída."
