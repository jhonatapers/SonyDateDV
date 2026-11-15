# Sony DV Date

Aplicação para recuperar a data e a hora de gravação de vídeos DV e gravá-las
sobre a imagem, no estilo de uma filmadora Sony. O arquivo original não é
alterado: o resultado é salvo em outro AVI.

## O que faz

- Lê os metadados de gravação de cada quadro de um AVI DV capturado de uma
  fita MiniDV ou Digital8.
- Exibe data e hora no canto inferior esquerdo, usando a fonte incluída no
  projeto, mês em inglês e relógio de 12 horas.
- Oferece interface gráfica para converter vários arquivos e uma opção de
  linha de comando.

São aceitos vídeos **DV25 PAL** (25 fps) e **NTSC** (30000/1001 fps), com
taxa constante. A data vem dos metadados DV, não da data do arquivo nem do
timecode da fita, e depende do relógio configurado na câmera. Quadros sem data
válida ficam sem texto; se nenhum quadro tiver data válida, a conversão falha.
Anos de 95 a 99 são interpretados como 1995 a 1999, e de 00 a 94 como 2000
a 2094.

O vídeo é desentrelaçado e recodificado em DV, e as faixas de áudio são
convertidas para PCM de 16 bits. A leitura das datas percorre o arquivo inteiro
antes da conversão. Reserve espaço em disco para o novo vídeo e mantenha uma
cópia do original.

## Requisitos

- Python 3.10 ou superior, com Tkinter para a interface gráfica.
- FFmpeg e FFprobe disponíveis no `PATH`. O FFmpeg deve incluir os filtros
  `ass` e `bwdif`, os codificadores `dvvideo` e `pcm_s16le`, e o muxer `data`.
- O arquivo `fonts\sonycam-original.ttf`, incluído no projeto. A fonte é
  carregada automaticamente, sem instalação no sistema.

O código da aplicação usa apenas a biblioteca padrão do Python. Para verificar
as ferramentas no PowerShell:

```powershell
python --version
python -m tkinter
ffmpeg -version
ffprobe -version
```

O comando do Tkinter abre uma pequena janela de teste. Se FFmpeg ou FFprobe não
forem encontrados, instale uma distribuição adequada e adicione sua pasta
`bin` ao `PATH`.

## Como usar

### Interface gráfica

Na pasta do projeto, execute:

```powershell
python run_gui.py
```

Adicione os arquivos AVI, selecione a pasta de destino e clique em
**Converter**. A interface mostra o andamento por arquivo. Se um arquivo
falhar, a conversão é interrompida e o erro é exibido.

### Linha de comando

```powershell
python sony_dv_date.py "C:\videos\filmagem.avi"
```

Por padrão, o resultado é criado em `out\filmagem.avi`, relativo ao diretório
atual. Para escolher o arquivo de saída:

```powershell
python sony_dv_date.py "C:\videos\filmagem.avi" -o "C:\videos\resultado.avi"
```

A saída deve ter extensão `.avi`. O programa não sobrescreve um arquivo
existente e não permite usar o próprio arquivo de entrada como destino. Use
`python sony_dv_date.py --help` para consultar as opções.

## Testes

Execute os testes automatizados na pasta do projeto:

```powershell
python -m unittest discover -s tests -v
```

Os testes não exigem vídeos reais nem executam uma conversão completa com
FFmpeg.

## Gerar executável para Windows

O empacotamento exige Python com Tkinter e uma distribuição do FFmpeg com
`ffmpeg.exe` e `ffprobe.exe` autossuficientes e os recursos descritos acima.
No PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build_windows.ps1
```

O script procura FFmpeg e FFprobe no `PATH`. Para usar outra distribuição:

```powershell
.\build_windows.ps1 -FFmpegDir "C:\caminho\para\bin"
```

O resultado é `dist\SonyDVDate.exe`, um executável com interface gráfica que
inclui Python, Tkinter, a fonte, FFmpeg e FFprobe. O script não sobrescreve um
executável existente nesse caminho. O programa extrai seus arquivos para uma
pasta temporária ao iniciar; compile e teste na arquitetura e versão do
Windows de destino.

As pastas `.venv`, `build`, `dist`, `in` e `out`, caches Python e arquivos AVI
são ignorados pelo Git. Os testes em `tests` fazem parte do projeto e devem
ser versionados.

## Licenças e distribuição

A fonte [SonyCam Original](https://fontstruct.com/fontstructions/show/1646448),
criada por Xane Myers, está licenciada sob
[Creative Commons Atribuição-CompartilhaIgual 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
Essa licença se aplica à fonte incluída em `fonts\sonycam-original.ttf`.

Antes de redistribuir o executável, cumpra também os termos do Python,
PyInstaller e da distribuição específica do FFmpeg, incluindo bibliotecas
integradas, avisos e eventuais obrigações de disponibilização do código-fonte.
O script de empacotamento não reúne esses materiais automaticamente. Uma
build do FFmpeg com `--enable-gpl`, por exemplo, exige atenção aos termos GPL.
