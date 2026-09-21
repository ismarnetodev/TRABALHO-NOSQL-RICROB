# GeoLog

Plataforma Streamlit de monitoramento geoespacial de uma frota logística. O projeto demonstra persistência poliglota: o SQLite mantém os dados cadastrais e transacionais, enquanto o MongoDB armazena a telemetria com coordenadas GeoJSON e consultas geoespaciais.

## Funcionalidades

- Inicialização automática do SQLite, MongoDB, coleções, índices e dados demonstrativos.
- Busca de veículos por raio usando o operador `$near` do MongoDB.
- Mapa interativo com Folium, ponto de referência, área do raio e marcadores dos veículos.
- Join em memória entre motoristas e veículos do SQLite e a leitura mais recente de cada veículo no MongoDB.
- Dashboard com frotas ativas, temperatura média da carga e alertas de velocidade acima de 80 km/h.
- Histórico de temperatura por veículo e distribuição do status dos motoristas com Plotly.
- Simulação de movimentação ao longo das rotas cadastradas e reset da telemetria inicial.

## Tecnologias

- Python 3.12+
- Streamlit
- SQLite (`sqlite3`)
- MongoDB (`pymongo`)
- Folium e `streamlit-folium`
- Plotly e Pandas
- `uv` para gerenciamento do ambiente e das dependências

## Pré-requisitos

1. Instale o Python 3.12 ou superior.
2. Instale o [MongoDB Community Server](https://www.mongodb.com/try/download/community) e mantenha o serviço disponível antes de iniciar a aplicação.
3. Instale o `uv` e sincronize as dependências:

   ```bash
   uv sync
   ```

Por padrão, a aplicação conecta em `mongodb://localhost:27017`. Para usar outra instância, configure `MONGODB_URI` antes da execução.

No PowerShell:

```powershell
$env:MONGODB_URI = "mongodb://usuario:senha@servidor:27017"
```

## Execução

Com o MongoDB disponível, execute:

```bash
uv run streamlit run app.py
```

O Streamlit exibirá a URL local da aplicação. Na primeira execução:

- o arquivo `logitech.db` é criado na raiz do projeto;
- as tabelas `motoristas` e `veiculos` recebem o seed apenas se estiverem vazias;
- o banco `geolog_db` e a coleção `telemetria` são utilizados no MongoDB;
- o índice geoespacial `location_2dsphere` é criado por código;
- as leituras de telemetria são inseridas apenas quando a coleção está vazia.

## Uso da aplicação

Na barra lateral, informe longitude, latitude e raio de busca. A consulta aceita raio entre 0,5 km e 50 km e usa coordenadas no formato GeoJSON `[longitude, latitude]`.

- **Simular movimentação**: gera uma nova leitura para cada veículo, avança sua posição na rota e varia temperatura e velocidade dentro dos limites definidos pela aplicação.
- **Resetar telemetria em vias públicas**: remove as leituras atuais e restaura o seed inicial.

## Persistência poliglota

### SQLite

O arquivo `logitech.db` contém:

- `motoristas`: `id`, `nome`, `cnh` e `status`;
- `veiculos`: `id`, `placa`, `modelo` e `motorista_id`, com chave estrangeira para `motoristas`.

### MongoDB

A coleção `geolog_db.telemetria` armazena documentos com esta estrutura:

```json
{
  "veiculo_id": 101,
  "location": {
    "type": "Point",
    "coordinates": [-34.878, -7.12]
  },
  "temperatura": 4.2,
  "velocidade": 65,
  "timestamp": "2026-09-11T10:00:00Z"
}
```

Além do índice `2dsphere` em `location`, é criado um índice composto por `veiculo_id` e `timestamp` para apoiar a recuperação das leituras.

## Estrutura do projeto

```text
app.py                                      # Entrada do Streamlit
pyproject.toml                              # Metadados e dependências
src/trabalho_nosql_ricrob/
├── __init__.py                             # Interface, mapa e dashboard
├── config.py                                # Configuração do MongoDB
├── fleet_service.py                         # SQLite, seed e dados da frota
├── routes.py                                # Rotas e avanço dos veículos
└── telemetry_service.py                     # MongoDB, GeoJSON e telemetria
```

O arquivo `logitech.db` é criado em tempo de execução e não faz parte do código-fonte versionado.