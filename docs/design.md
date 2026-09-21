# Design: automação local de planilhas e CSV

> Documento escrito **antes** da implementação, preservado como estava. O tempo
> futuro no texto é proposital: ele registra o que foi decidido antes de existir
> código, não o que o produto virou.
>
> O que mudou no caminho:
>
> - **Apelidos de coluna** não estavam previstos. Sem eles, um arquivo que
>   escreve `E-mail do Cliente` em vez de `email` era recusado inteiro — o que
>   inviabilizava o caso de uso real que motivou o projeto.
> - **A leitura de CSV não usa `pandas.read_csv`.** Ele converte `NA`, `NULL` e
>   `N/A` em valor ausente e não reporta a linha física verdadeira; os dois
>   corrompem dado em silêncio. A leitura passou a usar o módulo `csv` da
>   biblioteca padrão.
> - **A demonstração ganhou versão para Linux e macOS**, além do PowerShell.
> - **Licença MIT, integração contínua e lint** entraram depois, para o
>   repositório poder ser avaliado e adotado por terceiros.
> - A suíte terminou com **77 testes**, verificados por mutação.


Data: 20 de setembro de 2026

## Objetivo

Criar uma demonstração de portfólio pequena, executável e verificável para oferecer serviços de automação de planilhas. A ferramenta receberá arquivos CSV e XLSX, consolidará os registros, aplicará transformações seguras configuradas pelo usuário e produzirá um relatório Excel com dados válidos, erros e resumo da execução.

O projeto será independente do CheckCompany e funcionará integralmente no computador do cliente, sem servidor, domínio, banco de dados ou serviço pago.

## Público e proposta de valor

O público inicial são pequenos negócios e profissionais que repetem tarefas manuais em Excel, como juntar arquivos mensais, conferir campos obrigatórios, localizar duplicidades e preparar uma base única para análise.

A demonstração precisa provar três capacidades:

1. reduzir uma tarefa repetitiva a um único comando;
2. preservar a origem dos dados e explicar cada rejeição;
3. entregar um arquivo que uma pessoa não técnica consiga abrir no Excel.

## Escopo da primeira versão

A primeira versão deverá:

- localizar arquivos `.csv` e `.xlsx` em uma pasta de entrada;
- ler a primeira planilha de cada XLSX;
- ler CSV em `UTF-8`/`UTF-8 com BOM`, detectar os separadores vírgula ou ponto e vírgula e aceitar `Windows-1252` somente como fallback acompanhado de aviso;
- normalizar cabeçalhos removendo espaços laterais e acentos, convertendo para minúsculas e usando nomes no formato `snake_case`;
- remover espaços laterais de valores textuais sem modificar o conteúdo interno;
- preservar a procedência de cada registro nas colunas técnicas `origem_arquivo`, `origem_planilha` e `origem_linha`;
- validar colunas obrigatórias definidas em `config.json`;
- identificar duplicidades pelas colunas-chave configuradas;
- converter apenas os tipos declarados na configuração: texto, inteiro, decimal brasileiro e data brasileira;
- separar registros válidos de registros com erro;
- gerar um arquivo XLSX com as abas `dados_limpos`, `erros` e `resumo`;
- registrar no resumo a quantidade de arquivos encontrados, arquivos processados, registros lidos, registros válidos, registros inválidos e duplicidades;
- encerrar com código diferente de zero quando não houver entrada válida ou quando a configuração estiver incorreta;
- funcionar sem conexão com a internet.

## Fora do escopo

Esta versão não terá:

- interface web ou aplicativo móvel;
- dashboard visual;
- integração com Google Drive, APIs ou bancos de dados;
- automação de sites ou sistemas de terceiros;
- leitura de arquivos protegidos por senha;
- preservação ou execução de macros VBA;
- interpretação automática de regras de negócio;
- processamento de dados reais de clientes no repositório;
- envio automático de arquivos ou propostas comerciais.

Esses itens poderão virar trabalhos personalizados depois que o exemplo básico estiver validado.

## Abordagens consideradas

### Script único

Seria o caminho mais rápido, mas misturaria leitura, limpeza, validação e geração do relatório em um arquivo difícil de testar e adaptar. Foi descartado como base de portfólio.

### Aplicação desktop com interface gráfica

Seria mais fácil para alguns clientes finais, mas adicionaria empacotamento, estado de interface e suporte específico por sistema operacional antes de validarmos a demanda. Fica como evolução futura.

### CLI modular em Python — escolhida

Uma ferramenta de linha de comando permite uma demonstração confiável, testes automatizados e adaptação rápida para novos clientes. Um script PowerShell de exemplo oferecerá execução simples no Windows sem esconder o comando real.

## Interface de uso

O comando principal será:

```powershell
python -m automacao_planilhas processar `
  --entrada .\exemplos\entrada `
  --config .\exemplos\config.json `
  --saida .\exemplos\saida\relatorio.xlsx
```

Por segurança, um arquivo de saída existente não será substituído sem a opção `--sobrescrever`.

O arquivo de configuração terá estrutura semelhante a:

```json
{
  "colunas_obrigatorias": ["nome", "email", "data", "valor"],
  "chaves_duplicidade": ["email", "data"],
  "tipos": {
    "nome": "texto",
    "email": "texto",
    "data": "data_br",
    "valor": "decimal_br"
  }
}
```

O schema da configuração será validado antes da leitura dos dados. Nomes de colunas desconhecidos, tipos não suportados e configurações contraditórias produzirão uma mensagem objetiva e impedirão uma saída parcial enganosa.

## Arquitetura

O código será dividido em unidades pequenas:

- `cli.py`: interpreta os argumentos, coordena a execução e define códigos de saída;
- `config.py`: carrega e valida o JSON de configuração;
- `readers.py`: descobre e lê CSV/XLSX, incluindo metadados de procedência;
- `normalizer.py`: normaliza cabeçalhos, textos e tipos explicitamente configurados;
- `validator.py`: verifica campos obrigatórios e duplicidades;
- `report.py`: gera o XLSX final e o resumo;
- `models.py`: contém os tipos compartilhados e os resultados de processamento.

Essas unidades não acessarão a rede. A coordenação receberá caminhos explícitos, o que permitirá testar cada etapa com diretórios temporários.

## Fluxo de dados

1. A CLI valida caminhos, argumentos e configuração.
2. O leitor enumera arquivos suportados em ordem alfabética para tornar o resultado determinístico.
3. Cada origem é convertida para uma tabela comum e recebe as colunas de procedência.
4. Os cabeçalhos e valores textuais passam pelas transformações seguras.
5. As conversões de tipo declaradas são aplicadas. Falhas viram erros associados à linha original.
6. O validador detecta campos ausentes e duplicidades. Para uma chave repetida, a primeira ocorrência permanece válida e as seguintes são marcadas como duplicadas.
7. Linhas sem erro seguem para `dados_limpos`; as demais seguem para `erros` com `codigo_erro` e `detalhe_erro`.
8. O gerador grava as três abas em um arquivo temporário e só então move o resultado concluído para o destino, evitando arquivos finais corrompidos.

## Tratamento de erros

- Configuração inválida ou pasta inexistente: interrompe antes do processamento.
- Nenhum arquivo suportado: interrompe com orientação sobre os formatos aceitos.
- Arquivo individual ilegível: registra o problema no resumo e continua se existir ao menos uma origem válida.
- Cabeçalhos diferentes que resultem no mesmo nome normalizado: rejeita a origem e informa os cabeçalhos em conflito.
- Coluna obrigatória ausente em uma origem: rejeita os registros dessa origem com erro de schema, sem inventar valores.
- Valor incompatível com o tipo declarado: preserva o valor original na aba de erros.
- Falha ao gerar o XLSX: remove o arquivo temporário e não altera um relatório anterior.
- Saída já existente: interrompe, salvo quando `--sobrescrever` for informado.

Mensagens destinadas ao usuário serão em português e não exibirão rastreamento interno por padrão. A opção `--debug` habilitará detalhes técnicos.

Cada registro de entrada aparecerá no máximo uma vez na aba `erros`. Quando uma linha tiver mais de um problema, `codigo_erro` e `detalhe_erro` conterão listas separadas por ponto e vírgula. As métricas distinguirão quantidade de linhas inválidas de quantidade total de problemas encontrados.

## Segurança e privacidade

- Todo processamento será local.
- Os exemplos usarão apenas dados fictícios.
- A documentação orientará o usuário a trabalhar sobre uma cópia dos arquivos originais.
- Logs não incluirão o conteúdo completo das linhas; apenas arquivo, planilha, linha e código do erro.
- Nenhuma credencial será solicitada ou armazenada.
- Arquivos recebidos de futuros clientes não serão adicionados ao Git nem enviados para ferramentas de IA sem autorização expressa.

## Estrutura prevista

```text
portfolio-automacoes/
├── docs/
├── src/automacao_planilhas/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── normalizer.py
│   ├── readers.py
│   ├── report.py
│   └── validator.py
├── tests/
├── exemplos/
│   ├── entrada/
│   ├── saida/
│   └── config.json
├── executar-exemplo.ps1
├── pyproject.toml
├── README.md
└── .gitignore
```

## Testes e verificação

Os testes unitários cobrirão:

- normalização de cabeçalhos;
- limpeza conservadora de texto;
- conversão de inteiro, decimal e data;
- validação do `config.json`;
- detecção de campos obrigatórios vazios;
- duplicidades simples e compostas;
- preservação da origem de cada linha;
- proteção contra sobrescrita.

Um teste de integração criará arquivos CSV e XLSX temporários, executará o fluxo completo e verificará nomes das abas, contagens do resumo e separação entre linhas válidas e inválidas.

A demonstração será considerada pronta quando, em um ambiente Python limpo:

1. a instalação das dependências funcionar;
2. todos os testes passarem;
3. `executar-exemplo.ps1` gerar o relatório esperado;
4. nenhuma conexão de rede for necessária;
5. o README permitir que outra pessoa repita o exemplo sem orientação adicional.

## Entrega comercial posterior

O repositório demonstrará capacidade técnica, mas não prometerá uma solução universal. Cada proposta futura deverá delimitar os formatos de entrada, regras de negócio, volume, prazo, revisões e manutenção. O uso de IA será informado quando solicitado pelo cliente ou exigido pela plataforma, e qualquer restrição de confidencialidade terá precedência.
