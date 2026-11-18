# Fibra no Município

Diretório estático, em pt-BR, de prestadoras de **banda larga fixa em fibra** por município brasileiro. Os números vêm de dados abertos da Anatel e de estimativas do IBGE. **Este site não é a Anatel.**

Endereço público: <https://advogadomarciopinheiro-cmd.github.io/fibra-no-municipio/>

Não há preços, planos nem cobertura por bairro ou CEP. O CEP, quando usado, só descobre o município.

## Como gerar (local)

```bash
# 1) Baixar e processar os arquivos oficiais (reutiliza o que já estiver em data/raw/)
python3 scripts/fetch_and_process.py

# 2) Gerar o HTML estático em site/
#    Sem variáveis, o site assume a raiz (/), útil na prévia local.
python3 scripts/build.py

# 3) Prévia local
python3 -m http.server 8080 --directory site
```

Para gerar já no caminho do GitHub Pages:

```bash
export BASE_URL=/fibra-no-municipio/
export SITE_URL=https://advogadomarciopinheiro-cmd.github.io/fibra-no-municipio
python3 scripts/build.py
```

Atualizar os ZIPs da Anatel (em vez de reutilizar o cache):

```bash
python3 scripts/fetch_and_process.py --refresh
python3 scripts/build.py
```

Os arquivos brutos em `data/raw/` (centenas de MB) **não entram no git**. Os JSON processados em `data/processed/` entram, para o roteiro noturno conseguir publicar a próxima cidade sem baixar tudo de novo.

## Publicar no GitHub Pages e roteiro noturno

O conteúdo público vive na branch `gh-pages` (raiz do site, com `.nojekyll`). O código-fonte e os dados processados ficam em `main`.

```bash
# Acrescenta uma cidade, reconstrói com o BASE_URL do Pages e faz push
# só se houver mudança. A URL da página nova é registrada no log.
./publish_nightly.sh
```

O script chama `nightly.py` (idempotente: uma página nova por execução, sem duplicar município) e depois envia `main` e `gh-pages` se algo tiver mudado.

Só o roteiro, sem publicar:

```bash
export BASE_URL=/fibra-no-municipio/
export SITE_URL=https://advogadomarciopinheiro-cmd.github.io/fibra-no-municipio
python3 nightly.py
```

## Fontes

- Anatel, acessos de banda larga fixa (SCM): <https://www.anatel.gov.br/dadosabertos/paineis_de_dados/acessos/acessos_banda_larga_fixa.zip>
- Anatel, indicadores RQUAL: <https://www.anatel.gov.br/dadosabertos/paineis_de_dados/qualidade/indicadores_rqual.zip>
- Anatel, Selos e IQS: <https://www.anatel.gov.br/dadosabertos/paineis_de_dados/qualidade/indices_selos.zip>
- IBGE, estimativas de população (agregado 6579, variável 9324)

Fibra = campo `Meio de Acesso` igual a `Fibra`. O recorte residencial usado nas participações é pessoa física + produto INTERNET + meio fibra.

Links comerciais de afiliados, quando existirem, terão o rótulo visível **Publicidade** (CONAR). Neste momento esses espaços estão vazios.
