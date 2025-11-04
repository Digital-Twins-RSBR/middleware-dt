#!/bin/bash

echo "🔍 Verificando serviços obrigatórios do MidDiTS..."

# PostgreSQL
echo -n "PostgreSQL: "
docker exec middleware-dt_db_1 pg_isready -U postgres > /dev/null 2>&1 && echo "OK" || echo "FALHOU"

# Neo4j
echo -n "Neo4j: "
docker exec middleware-dt_neo4j_1 cypher-shell -u neo4j -p password 'RETURN 1' > /dev/null 2>&1 && echo "OK" || echo "FALHOU"

# InfluxDB
echo -n "InfluxDB: "
curl -s http://localhost:8086/health | grep '"status":"pass"' > /dev/null 2>&1 && echo "OK" || echo "FALHOU"

# Parser
echo -n "Parser API: "
curl -s http://localhost:8082/swagger/index.html| grep -i 'html' > /dev/null 2>&1 && echo "OK" || echo "FALHOU"

echo "✅ Verificação concluída."
