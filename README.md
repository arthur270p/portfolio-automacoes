# Automação de planilhas

Junta vários arquivos CSV e Excel numa base única, separa o que está bom do que tem problema, e explica cada rejeição apontando o arquivo e a linha de origem.

Roda inteiramente no seu computador. Sem servidor, sem nuvem, sem internet.

## O problema

Todo mês chega a mesma tarefa: abrir seis planilhas, empilhar no Excel, procurar campo vazio, caçar lançamento repetido, arrumar data e valor que vieram em formato diferente. Leva horas, e o erro só aparece depois — quando alguém pergunta por que o total não fecha.

Esta ferramenta reduz isso a um comando, e entrega um relatório que diz exatamente o que entrou, o que ficou de fora e por quê.

## O que ela faz

- lê `.csv` e `.xlsx` de uma pasta, em ordem alfabética, sempre igual;
- aceita CSV em UTF-8 (com ou sem BOM), separado por vírgula ou ponto e vírgula, e cai para Windows-1252 com aviso registrado;
- padroniza os cabeçalhos: sem acento, sem espaço nas pontas, minúsculas, `snake_case`;
- guarda a procedência de cada linha em `origem_arquivo`, `origem_planilha` e `origem_linha`;
- confere as colunas obrigatórias que você declarou;
- acha repetições da chave que você definiu, mantendo a primeira ocorrência;
- converte só os tipos que você declarou: texto, inteiro, decimal e data brasileiros;
- entrega um Excel com três abas: `dados_limpos`, `erros` e `resumo`.

## O que ela não faz

Não abre arquivo protegido por senha, não executa nem preserva macros, não conversa com Google Drive nem com nenhuma API, não adivinha regra de negócio e não interpreta coluna que você não declarou. Lê apenas a **primeira aba** de cada arquivo Excel.

## Instalação

Precisa de Python 3.12 ou mais novo.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
```

## Uso

```powershell
python -m automacao_planilhas processar `
  --entrada .\exemplos\entrada `
  --config .\exemplos\config.json `
  --saida .\exemplos\saida\relatorio.xlsx
```

Um relatório que já existe **não** é substituído sem `--sobrescrever`. A opção `--debug` mostra o detalhe técnico quando algo inesperado acontece.

## Demonstração

```powershell
.\executar-exemplo.ps1
```

Os arquivos de `exemplos/entrada` têm cinco linhas fictícias, escolhidas para exercitar cada caminho: duas corretas, uma sem e-mail, uma com valor que não é número, e uma venda lançada duas vezes em arquivos diferentes.

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
  }
}
```

| campo | o que faz |
| --- | --- |
| `colunas_obrigatorias` | linha sem algum desses campos vai para `erros` |
| `chaves_duplicidade` | o conjunto que define "é o mesmo registro" |
| `tipos` | só as colunas listadas são convertidas |

Tipos aceitos: `texto`, `inteiro`, `decimal_br` (`1.234,56`) e `data_br` (`dd/mm/aaaa`). Os nomes das colunas seguem o padrão já normalizado: minúsculas, sem acento, com `_` no lugar do espaço.

A configuração é validada **antes** de qualquer arquivo ser lido. Nome de coluna fora do padrão, tipo desconhecido ou chave desconhecida interrompem a execução sem gerar relatório pela metade.

## As três abas

**`dados_limpos`** — as linhas sem nenhum problema, com as colunas de procedência. Data e valor saem como data e número do Excel, não como texto: dá para somar, ordenar e filtrar.

**`erros`** — cada linha problemática aparece **uma vez**, com todos os seus problemas em `codigo_erro` e `detalhe_erro`, separados por ponto e vírgula. O valor original é preservado como veio.

**`resumo`** — as sete métricas e uma linha por arquivo que gerou aviso ou foi recusado. Arquivo rejeitado aparece pelo nome, não só na contagem.

## Códigos de saída

| código | significado |
| --- | --- |
| 0 | processou |
| 1 | falha inesperada |
| 2 | argumento, configuração ou pasta de entrada inválida |
| 3 | nenhuma origem válida |
| 4 | o relatório já existe e `--sobrescrever` não foi informado |

## Privacidade

Tudo acontece na sua máquina. Nenhum dado sai do computador, nenhuma credencial é pedida ou guardada, e a ferramenta não faz chamada de rede em nenhum momento.

Os registros de execução trazem arquivo, planilha, linha e código do erro — nunca o conteúdo da linha.

**Trabalhe sempre sobre uma cópia.** A ferramenta não altera os arquivos de entrada, mas a regra vale para qualquer processamento: o original fica intocado, em outro lugar.

Os arquivos em `exemplos/` são fictícios. Dado real de cliente não entra neste repositório.

## Testes

```powershell
python -m pytest
```

## Sobre trabalhos sob medida

Este repositório demonstra o método: leitura conservadora, procedência preservada, erro explicado e saída auditável. Ele não é uma solução universal.

Cada projeto tem formato de entrada, regra de negócio e volume próprios. Escopo, prazo, revisões, manutenção e confidencialidade são combinados caso a caso, por escrito, antes de começar. O uso de ferramentas de IA no desenvolvimento é informado quando o cliente pergunta ou quando a plataforma exige, e qualquer restrição de sigilo do cliente tem precedência.
