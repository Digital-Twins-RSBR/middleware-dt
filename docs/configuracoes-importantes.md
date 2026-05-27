# Configurações Importantes

O device type e o device do módulo facade possuem o campo `inactivityTimeout`, que define o tempo de inatividade de um device. O tempo padrão do MidDTS pode ser redefinido no settings por meio da configuração `DEFAULT_INACTIVITY_TIMEOUT`.

[Voltar para a documentação principal](../README.md#configuracoes-importantes)

Sugestões de faixa por perfil:

- Sensores críticos: 15-30 segundos
- Dispositivos de baixa prioridade: 120-300 segundos
- Dispositivos com bateria limitada: 300-600 segundos
