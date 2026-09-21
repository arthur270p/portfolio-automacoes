# Automação de planilhas

[![CI](https://github.com/arthur270p/portfolio-automacoes/actions/workflows/ci.yml/badge.svg)](https://github.com/arthur270p/portfolio-automacoes/actions/workflows/ci.yml)
[![Licença: MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue.svg)](LICENSE)

Junta vários arquivos CSV e Excel numa base única, separa o que está bom do que tem problema, e explica cada rejeição apontando o arquivo e a linha de origem.

Roda inteiramente no seu computador. Sem servidor, sem nuvem, sem internet.

## Avalie em dois minutos

```bash
git clone https://github.com/arthur270p/portfolio-automacoes.git
cd portfolio-automacoes
python -m pip install -e ".[dev]"
python -m pytest          # 77 testes
./executar-exemplo.sh     # no Windows: .\executar-exemplo.ps1
```

O relatório sai em `exemplos/saida/relatorio.xlsx`. Abra: cinco linhas entraram, duas passaram, três foram recusadas, e a aba `erros` diz o arquivo e a linha de cada uma.

Se for olhar o código, três lugares mostram como as decisões foram tomadas:

| arquivo | o que mostra |
| --- | --- |
| [`readers.py`](src/automacao_planilhas/readers.py) | por que a leitura de CSV não usa `pandas.read_csv` — dois modos de corromper dado em silêncio |
| [`report.py`](src/automacao_planilhas/report.py) | por que texto iniciado por `=` é neutralizado, e por que só o `=` |
| [`cli.py`](src/automacao_planilhas/cli.py) | como o relatório anterior sobrevive a uma falha no meio da escrita |

O documento de projeto está em [`docs/design.md`](docs/design.md): objetivo, alternativas descartadas e por quê, e — no topo — o que mudou entre o que foi planejado e o que foi construído.

## O problema

Todo mês chega a mesma tarefa: abrir seis planilhas, empilhar no Excel, procurar campo vazio, caçar lançamento repetido, arrumar data e valor que vieram em formato diferente. Leva horas, e o erro só aparece depois — quando alguém pergunta por que o total não fecha.

Esta ferramenta reduz isso a um comando, e entrega um relatório que diz exatamente o que entrou, o que ficou de fora e por quê.

## O que ela faz

- lê `.csv` e `.xlsx` de uma pasta, em ordem alfabética, sempre igual;
- aceita CSV em UTF-8 (com ou sem BOM), separado por vírgula ou ponto e vírgula, e cai para Windows-1252 com aviso registrado;
- padroniza os cabeçalhos: sem acento, sem espaço nas pontas, minúsculas, `snake_case`;
- reconhece a mesma coluna com nomes diferentes entre arquivos, por apelido declarado;
- guarda a procedência de cada linha em `origem_arquivo`, `origem_planilha` e `origem_linha`;
- confere as colunas obrigatórias que você declarou;
- acha repetições da chave que você definiu, mantendo a primeira ocorrência;
- converte só os tipos que você declarou: texto, inteiro, decimal e data brasileiros;
- entrega um Excel com três abas: `dados_limpos`, `erros` e `resumo`.

## O que ela não faz

Não abre arquivo protegido por senha, não executa nem preserva macros, não conversa com Google Drive nem com nenhuma API, não adivinha regra de negócio e não interpreta coluna que você não declarou. Lê apenas a **primeira aba** de cada arquivo Excel.

A comparação de chave é exata: `JOAO@X.COM` e `joao@x.com` são tratados como registros diferentes. Se suas chaves variam em maiúsculas, padronize os dados antes.

## Instalação

Precisa de Python 3.12 ou mais novo.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Depois disso, `automacao-planilhas` fica disponível como comando. Tudo aqui também funciona com `python -m automacao_planilhas`, sem instalar nada.

## Uso

```powershell
automacao-planilhas processar `
  --entrada .\exemplos\entrada `
  --config .\exemplos\config.json `
  --saida .\exemplos\saida\relatorio.xlsx
```

Um relatório que já existe **não** é substituído sem `--sobrescrever`. A opção `--debug` mostra o detalhe técnico quando algo inesperado acontece, e `--versao` informa a versão instalada.

## Demonstração

```powershell
.\executar-exemplo.ps1     # Windows
./executar-exemplo.sh      # Linux e macOS
```

Os arquivos de `exemplos/entrada` têm cinco linhas fictícias, escolhidas para exercitar cada caminho: duas corretas, uma sem e-mail, uma com valor que não é número, e uma venda lançada duas vezes em arquivos diferentes. Os dois arquivos **discordam no nome da coluna de e-mail**, como acontece quando vêm de sistemas diferentes.

O resumo do relatório sai assim:

| item | valor |
| --- | --- |
| arquivos_encontrados | 2 |
| arquivos_processados | 2 |
| registros_lidos | 5 |
| registros_validos | 2 |
| registros_invalidos | 3 |
| duplicidades | 1 |
| problemas_encontrados | 3 |

E a aba `erros` aponta cada caso:

```
linha 2 de vendas_fevereiro.csv   TIPO_DECIMAL_INVALIDO
linha 2 de vendas_janeiro.csv     REGISTRO_DUPLICADO
linha 4 de vendas_janeiro.csv     CAMPO_OBRIGATORIO_VAZIO
```

A venda repetida aparece marcada no arquivo de **janeiro** porque os arquivos são lidos em ordem alfabética, e `fevereiro` vem antes. A primeira ocorrência lida é a que permanece válida.

## Configuração

```json
{
  "colunas_obrigatorias": ["nome", "email", "data", "valor"],
  "chaves_duplicidade": ["email", "data"],
  "tipos": {
    "nome": "texto",
    "email": "texto",
    "data": "data_br",
    "valor": "decimal_br"
  },
  "apelidos": {
    "email": ["e_mail_do_cliente", "correio_eletronico"]
  }
}
```

| campo | o que faz |
| --- | --- |
| `colunas_obrigatorias` | linha sem algum desses campos vai para `erros` |
| `chaves_duplicidade` | o conjunto que define "é o mesmo registro" |
| `tipos` | só as colunas listadas são convertidas |
| `apelidos` | opcional: outros nomes pelos quais a coluna pode aparecer |

Tipos aceitos: `texto`, `inteiro`, `decimal_br` (`1.234,56`) e `data_br` (`dd/mm/aaaa`). Os nomes das colunas seguem o padrão já normalizado: minúsculas, sem acento, com `_` no lugar do espaço.

A configuração é validada **antes** de qualquer arquivo ser lido. Nome de coluna fora do padrão, tipo desconhecido ou chave desconhecida interrompem a execução sem gerar relatório pela metade.

### Apelidos de coluna

Planilhas de origens diferentes raramente concordam no nome da coluna. Sem apelido, um arquivo que escreve `E-mail do Cliente` em vez de `email` seria recusado inteiro — e você voltaria a consolidar na mão, que é o trabalho que a ferramenta existe para eliminar.

O apelido é escrito já normalizado, então uma única declaração de `e_mail_do_cliente` cobre `E-mail do Cliente`, `e-mail do cliente` e `E_Mail_Do_Cliente`.

Quando um arquivo traz **dois candidatos** para a mesma coluna — o nome canônico e um apelido, ou dois apelidos — a origem é recusada com `APELIDO_AMBIGUO`, nomeando as duas colunas. A ferramenta não escolhe: escolher descartaria uma coluna inteira de dado real sem deixar rastro.

Ambiguidade na própria configuração — um apelido apontando para duas colunas, ou um apelido que já é o nome de outra coluna — é barrada no carregamento, antes de qualquer arquivo ser aberto.

## As três abas

**`dados_limpos`** — as linhas sem nenhum problema, com as colunas de procedência. Data e valor saem como data e número do Excel, não como texto: dá para somar, ordenar e filtrar.

**`erros`** — cada linha problemática aparece **uma vez**, com todos os seus problemas em `codigo_erro` e `detalhe_erro`, separados por ponto e vírgula. O valor original é preservado como veio.

**`resumo`** — as sete métricas e uma linha por arquivo que gerou aviso ou foi recusado. Arquivo rejeitado aparece pelo nome, não só na contagem.

## Códigos

Todo problema sai identificado por um código estável, para poder ser filtrado no Excel ou tratado por script.

**Por linha**, na aba `erros`:

| código | quando aparece |
| --- | --- |
| `CAMPO_OBRIGATORIO_VAZIO` | coluna obrigatória em branco |
| `REGISTRO_DUPLICADO` | repetição da chave; a primeira ocorrência fica |
| `TIPO_TEXTO_INVALIDO` | valor não convertível para texto |
| `TIPO_INTEIRO_INVALIDO` | valor não é inteiro |
| `TIPO_DECIMAL_INVALIDO` | valor fora de `1.234,56` |
| `TIPO_DATA_INVALIDO` | data fora de `dd/mm/aaaa` |

**Por arquivo**, na aba `resumo`:

| código | quando aparece |
| --- | --- |
| `ENCODING_CP1252` | aviso: o arquivo não era UTF-8 e foi lido como Windows-1252 |
| `COLUNA_OBRIGATORIA_AUSENTE` | falta uma coluna declarada, e nenhum apelido dela aparece |
| `APELIDO_AMBIGUO` | dois candidatos para a mesma coluna no mesmo arquivo |
| `CABECALHO_COLISAO` | dois cabeçalhos viram o mesmo nome ao normalizar |
| `COLUNA_RESERVADA` | o arquivo usa um nome de coluna de procedência |
| `ARQUIVO_ILEGIVEL` | corrompido, protegido por senha ou não é o formato que a extensão diz |

**Códigos de saída** do processo:

| código | significado |
| --- | --- |
| 0 | processou |
| 1 | falha inesperada |
| 2 | argumento, configuração ou pasta de entrada inválida |
| 3 | nenhuma origem válida |
| 4 | o relatório já existe e `--sobrescrever` não foi informado |

## Privacidade

Tudo acontece na sua máquina. Nenhum dado sai do computador, nenhuma credencial é pedida ou guardada, e a ferramenta não faz chamada de rede em nenhum momento.

Isso não é só uma promessa do texto: um dos testes bloqueia a criação de qualquer socket e roda o fluxo inteiro. Se alguma dependência tentasse abrir conexão, a suíte quebraria.

Os registros de execução trazem arquivo, planilha, linha e código do erro — nunca o conteúdo da linha.

**Trabalhe sempre sobre uma cópia.** A ferramenta não altera os arquivos de entrada, mas a regra vale para qualquer processamento: o original fica intocado, em outro lugar.

Os arquivos em `exemplos/` são fictícios. Dado real de cliente não entra neste repositório.

## Testes e qualidade

```powershell
python -m pytest        # 77 testes
python -m ruff check .  # lint
```

A CI roda os dois em Windows e Linux, no Python 3.12, 3.13 e 3.14, e executa a demonstração documentada acima — um portfólio que mostra uma demonstração quebrada é pior que um sem demonstração nenhuma.

Os testes foram verificados por mutação: cada proteção do código foi removida, uma por vez, para confirmar que algum caso realmente quebra. Três testes passaram verdes sem testar nada e só foram descobertos assim.

## Licença

MIT. Veja [LICENSE](LICENSE).

## Sobre trabalhos sob medida

Este repositório demonstra o método: leitura conservadora, procedência preservada, erro explicado e saída auditável. Ele não é uma solução universal.

Cada projeto tem formato de entrada, regra de negócio e volume próprios. Escopo, prazo, revisões, manutenção e confidencialidade são combinados caso a caso, por escrito, antes de começar. O uso de ferramentas de IA no desenvolvimento é informado quando o cliente pergunta ou quando a plataforma exige, e qualquer restrição de sigilo do cliente tem precedência.

Contato: [github.com/arthur270p](https://github.com/arthur270p)
