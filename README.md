# Trabalho Final: Comparativo de Bancos de Dados para Análise Geoespacial

Este projeto realiza uma análise comparativa entre MongoDB (NoSQL) e PostgreSQL com PostGIS (SQL) na manipulação e visualização de dados geoespaciais, especificamente acidentes de trânsito na região metropolitana de São Paulo.

## 🚀 Funcionalidades Principais

- **Upload de Dados**: O usuário pode fazer upload de arquivos CSV contendo dados georreferenciados.
- **Visualização Geoespacial**:
  - **Plotly**: Gera visualizações interativas de "Heatmaps" e "Mapas de Bolhas" para identificar concentrações de acidentes.
  - **Folium**: Exibe mapas interativos com marcadores e painéis informativos (Tooltips) para cada ponto de acidente.
- **Análise Comparativa**:
  - Compara o desempenho de consultas de alta cardinalidade e agrupamento (group by) entre MongoDB e PostgreSQL.
  - Calcula e exibe métricas de performance (tempo de execução) para auxiliar na escolha tecnológica.

## 🛠️ Tecnologias Utilizadas

### Frontend e Visualização
- **Streamlit**: Framework Python para criação da interface web.
- **Plotly**: Biblioteca de visualização de dados interativos.
- **Folium**: Visualização baseada em Leaflet.js, ideal para mapas.

### Backend e Banco de Dados
- **MongoDB**: Banco de dados NoSQL orientado a documentos.
- **PostgreSQL + PostGIS**: Banco de dados relacional com extensão geoespacial.

### Processamento de Dados
- **Pandas**: Manipulação e pré-processamento de dados (CSV).
- **SQLAlchemy**: ORM e driver SQL para interação com o PostgreSQL.

## 🏃 Como Executar

1.  **Instalação de Dependências**:
    Certifique-se de ter o Python 3.12+ instalado. Use o `uv` para instalar as dependências listadas no `pyproject.toml`:
    ```bash
    uv sync
    ```

2.  **Execução da Aplicação**:
    Inicie o servidor Streamlit:
    ```bash
    uv run streamlit run app.py
    ```

## 📁 Estrutura do Projeto

- `app.py`: Ponto de entrada da aplicação Streamlit.
- `src/`: Código fonte backend.
  - `mongodb_service.py`: Lógica de conexão e consulta ao MongoDB.
  - `postgresql_service.py`: Lógica de conexão e consulta ao PostgreSQL/PostGIS.
  - `data_loader.py`: Funções para carregamento e pré-processamento de CSV.
