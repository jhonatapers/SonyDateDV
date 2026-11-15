"""Grava a data original de um AVI DV sobre um novo video."""

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path


class VideoError(Exception):
    pass


def bcd(value: int, mask: int) -> int:
    value &= mask
    if value & 15 > 9:
        raise ValueError("BCD invalido")
    return (value >> 4) * 10 + (value & 15)


def recording_date(frame: bytes) -> dt.datetime | None:
    """Le os pacotes de data e hora do subcodigo de um quadro DV25."""
    packs: dict[int, bytes] = {}
    for sequence in range(len(frame) // 12000):
        for block in (1, 2):
            for slot in range(6):
                offset = sequence * 12000 + block * 80 + 6 + slot * 8
                pack = frame[offset : offset + 5]
                if pack[0] in (0x62, 0x63):
                    packs.setdefault(pack[0], pack)
        if 0x62 in packs and 0x63 in packs:
            break
    if 0x62 not in packs or 0x63 not in packs:
        return None
    date, time = packs[0x62], packs[0x63]
    try:
        year = bcd(date[4], 0xFF)
        return dt.datetime(
            2000 + year if year < 95 else 1900 + year,
            bcd(date[3], 0x1F),
            bcd(date[2], 0x3F),
            bcd(time[4], 0x3F),
            bcd(time[3], 0x7F),
            bcd(time[2], 0x7F),
        )
    except ValueError:
        return None


def read_exact(stream, size: int) -> bytes:
    chunks = []
    while size:
        chunk = stream.read(size)
        if not chunk:
            break
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


def probe(path: Path, *, creationflags: int = 0) -> Fraction:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,r_frame_rate,avg_frame_rate",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True, creationflags=creationflags,
    )
    streams = json.loads(result.stdout)["streams"]
    if not streams or streams[0].get("codec_name") != "dvvideo":
        raise VideoError("A entrada precisa conter video DV.")
    try:
        fps = Fraction(streams[0]["r_frame_rate"])
        average = Fraction(streams[0]["avg_frame_rate"])
    except (KeyError, ValueError, ZeroDivisionError) as exc:
        raise VideoError("Nao foi possivel identificar a taxa de quadros.") from exc
    if fps not in (Fraction(25), Fraction(30000, 1001)) or average != fps:
        raise VideoError("Apenas DV25 com taxa de quadros constante e suportado.")
    return fps


def ass_time(frame_number: int | Fraction, fps: Fraction) -> str:
    centiseconds = int(Fraction(frame_number * 100, 1) / fps)
    seconds, cs = divmod(centiseconds, 100)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{seconds:02}.{cs:02}"


def camera_date_text(date: dt.datetime) -> str:
    months = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
              "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
    return f"{months[date.month - 1]} {date.day} {date.year}"


def camera_time_glyphs(date: dt.datetime) -> list[tuple[int, int, str]]:
    hour = date.hour % 12 or 12
    period = "AM" if date.hour < 12 else "PM"
    text = f"{hour:2}:{date.minute:02}:{date.second:02}"
    positions = (65, 90, 112, 134, 159, 180, 201, 226)
    glyphs = [(x, 38, char) for x, char in zip(positions, text) if char != " "]
    glyphs.append((262, 26, period))
    return glyphs


def extract_subtitles(
    source: Path, fps: Fraction, destination: Path, *, creationflags: int = 0
) -> tuple[int, int]:
    timing = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=time_base:format=start_time",
         "-of", "json", str(source)],
        capture_output=True, text=True, check=True, creationflags=creationflags,
    )
    try:
        info = json.loads(timing.stdout)
        time_base = Fraction(info["streams"][0]["time_base"])
        start_time = Fraction(info["format"]["start_time"])
        if time_base <= 0:
            raise ValueError("time_base invalido")
    except (KeyError, IndexError, ValueError, ZeroDivisionError) as exc:
        raise VideoError("Nao foi possivel identificar os tempos do video.") from exc

    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-i", str(source),
        "-map", "0:v:0", "-c", "copy", "-f", "data", "pipe:1",
    ]
    events: list[tuple[Fraction, Fraction, dt.datetime]] = []
    count = missing = 0
    previous = None
    start = end = Fraction(0)
    last_position = None
    with tempfile.TemporaryFile() as errors, tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as timestamps:
        subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_packets",
             "-show_entries", "packet=pts", "-of", "csv=p=0", str(source)],
            stdout=timestamps, stderr=subprocess.PIPE, text=True, check=True,
            creationflags=creationflags,
        )
        timestamps.seek(0)
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=errors, creationflags=creationflags
        )
        assert process.stdout is not None
        try:
            while True:
                header = read_exact(process.stdout, 4)
                if not header:
                    break
                if len(header) != 4:
                    raise VideoError("Quadro DV incompleto.")
                size = 144000 if header[3] & 0x80 else 120000
                if (size == 144000) != (fps == 25):
                    raise VideoError("O formato do quadro DV nao corresponde a taxa de quadros.")
                frame = header + read_exact(process.stdout, size - 4)
                if len(frame) != size:
                    raise VideoError("Quadro DV incompleto.")
                try:
                    position = (int(timestamps.readline().strip()) * time_base - start_time) * fps
                except ValueError as exc:
                    raise VideoError("Timestamp de quadro DV ausente ou invalido.") from exc
                if position < 0 or (last_position is not None and position <= last_position):
                    raise VideoError("Timestamps de quadros DV fora de ordem.")
                last_position = position
                end = position + 1
                current = recording_date(frame)
                missing += current is None
                if current != previous:
                    if previous is not None:
                        events.append((start, position, previous))
                    start, previous = position, current
                count += 1
            if timestamps.readline():
                raise VideoError("Quantidade de timestamps e quadros DV nao corresponde.")
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            process.stdout.close()
        code = process.wait()
        if code:
            errors.seek(0)
            raise VideoError("Falha ao extrair quadros DV: " + errors.read().decode(errors="replace").strip())
    if previous is not None:
        events.append((start, end, previous))
    if not events:
        raise VideoError("Nenhum quadro possui data e hora de gravacao DV validas.")

    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 480
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Data,SonyCam Original,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,92,0,0,1,2,0,2,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with destination.open("w", encoding="utf-8", newline="\n") as subtitles:
        subtitles.write(header)
        for first, last, date in events:
            lines = [(180, 414, 38, camera_date_text(date))]
            lines.extend(
                (x, 453, size, text)
                for x, size, text in camera_time_glyphs(date)
            )
            for x, y, size, text in lines:
                bold = r"\b1" if text in ("AM", "PM") else ""
                subtitles.write(
                    f"Dialogue: 0,{ass_time(first, fps)},{ass_time(last, fps)},"
                    f"Data,,0,0,0,,{{\\an2\\pos({x},{y})\\fs{size}{bold}}}{text}\n"
                )
    return count, missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Sobrepoe a data original de um AVI DV ao video.")
    parser.add_argument("entrada", type=Path, help="arquivo AVI com video DV")
    parser.add_argument("-o", "--saida", type=Path, help="arquivo AVI de saida (padrao: out/NOME.avi)")
    args = parser.parse_args()
    source = args.entrada.resolve()
    output = (args.saida or Path("out") / (source.stem + ".avi")).resolve()
    font = Path(__file__).resolve().parent / "fonts" / "sonycam-original.ttf"
    try:
        if not source.is_file():
            raise VideoError(f"Arquivo de entrada nao encontrado: {source}")
        if output.suffix.lower() != ".avi":
            raise VideoError("A saida deve ter extensao .avi.")
        if source == output or output.exists():
            raise VideoError(f"A saida ja existe ou coincide com a entrada: {output}")
        if not font.is_file():
            raise VideoError(f"Fonte nao encontrada: {font}")
        for tool in ("ffmpeg", "ffprobe"):
            if not shutil.which(tool):
                raise VideoError(f"{tool} nao encontrado no PATH.")
        fps = probe(source)
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="sony-dv-date-") as directory:
            temp = Path(directory)
            (temp / "fonts").mkdir()
            shutil.copy2(font, temp / "fonts" / font.name)
            print("Lendo datas dos quadros DV...", flush=True)
            frames, missing = extract_subtitles(source, fps, temp / "datas.ass")
            print(f"Quadros: {frames}; sem data valida: {missing}.", flush=True)
            if missing:
                print("Aviso: os quadros sem data valida ficarao sem texto.", file=sys.stderr)
            print("Gerando video...", flush=True)
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-nostdin", "-n", "-i", str(source),
                 "-map", "0:v:0", "-map", "0:a?", "-vf",
                 "bwdif=mode=send_frame:parity=auto:deint=interlaced,ass=datas.ass:fontsdir=fonts",
                 "-c:v", "dvvideo", "-pix_fmt", "yuv420p" if fps == 25 else "yuv411p",
                 "-c:a", "pcm_s16le",
                 str(output)],
                cwd=temp, check=True,
            )
        print(f"Video gerado: {output}")
        return 0
    except (VideoError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        print(f"Erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
