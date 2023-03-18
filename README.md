# bdtd-scraper

## Requisitos

* **Python 3** (>= 3.9)
* BeautifulSoup4 (>= 4.8.2)
* Pandas (>= 1.4.3)
* requests (>= 2.28.1)
* tqdm (>+4.64.0)

Para instalar as bibliotecas necessárias:

> `python3 -m pip install requirements.txt`

## Modo de uso

```
usage: bdtd.py [-h] [-o OUTPUT_FOLDER] [-p MAX_PAGES] [-t TYPE]
               [-w MAX_WORKERS] [--interval INTERVAL] [--retries MAX_RETRIES]
               search_term

positional arguments:
  search_term           Termo a ser pesquisado na BDTD

options:
  -h, --help            show this help message and exit
  -o OUTPUT_FOLDER, --output-folder OUTPUT_FOLDER
                        Nome da pasta de saída
  -p MAX_PAGES, --pages MAX_PAGES
                        Número de páginas a serem consideradas durante busca
                        (padrão: sem limite)
  -t TYPE, --type TYPE  Filtro a ser utilizado para busca por palavra-chave
                        (padrão: 'AllFields')
  -w MAX_WORKERS, --workers MAX_WORKERS
                        Número de tarefas a ser desempenhadas em coocorrência
                        (padrão: 8)
  --interval INTERVAL   Intervalo entre requisições (padrão: 0.5)
  --retries MAX_RETRIES
                        Número de tentativas antes de abortar pesquisa
                        (padrão: 3)
```

Um [Jupyter Notebook](notebook.ipynb) também encontra-se disponível com algumas instruções de uso.

### Exemplos

#### Via linha de comando (CLI)

Para pesquisar por dissertações e teses mencionando "coronavírus" em modo multiprocessamento (20):

> `python3 bdtd.py coronavírus --output BDTD-COVID --workers 20`

Uma nova pasta `BDTD-COVID` será criada com o(s) arquivo(s) de saída.

#### Utilizando como módulo

Para pesquisar por dissertações e teses mencionando "coronavírus" em modo multiprocessamento (20):

```
from bdtd import BDTD
bdtd = BDTD()
df = bdtd.search("coronavírus", parsed=True, workers=20)
```

Um objeto tipo `pandas.DataFrame` será retornado com os resultados da busca.

___

🇧🇷 Um projeto do [Sou Ciência - Universidade Federal de São Paulo (Unifesp)](https://souciencia.unifesp.br/).
