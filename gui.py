"""Interface gráfica para conversão de vídeos DV com timestamp."""

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from sony_dv_date import VideoError, extract_subtitles, probe
import shutil
import subprocess
import tempfile

NO_CONSOLE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class DVConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SonyDateDV Converter")
        self.root.geometry("600x450")
        self.root.resizable(True, True)
        self.root.minsize(500, 400)

        self.selected_files = []
        self.output_dir = None

        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(
            main_frame,
            text="SonyDateDV Converter",
            font=("Helvetica", 14, "bold")
        )
        title.pack(pady=(0, 8))

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

        self.btn_convert = ttk.Button(
            button_frame,
            text="▶ CONVERTER",
            command=self.start_conversion
        )
        self.btn_convert.pack(side=tk.LEFT)

        btn_cancel = ttk.Button(
            button_frame,
            text="✕ Sair",
            command=self.root.quit
        )
        btn_cancel.pack(side=tk.RIGHT)

        progress_frame = ttk.LabelFrame(main_frame, text="Conversão", padding="6")
        progress_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        self.status_label = ttk.Label(
            progress_frame,
            text="Pronto para converter",
            foreground="blue"
        )
        self.status_label.pack(anchor=tk.W)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate"
        )
        self.progress_bar.pack(fill=tk.X, pady=(4, 0))

        output_frame = ttk.LabelFrame(main_frame, text="Pasta de destino", padding="6")
        output_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))

        btn_select_output = ttk.Button(
            output_frame,
            text="Selecionar pasta",
            command=self.select_output_dir
        )
        btn_select_output.pack(side=tk.RIGHT, padx=(8, 0))

        self.output_label = ttk.Label(
            output_frame,
            text="Nenhuma pasta selecionada",
            foreground="gray"
        )
        self.output_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        input_frame = ttk.LabelFrame(main_frame, text="Vídeos AVI", padding="6")
        input_frame.pack(fill=tk.BOTH, expand=True)

        input_buttons = ttk.Frame(input_frame)
        input_buttons.pack(fill=tk.X, pady=(0, 6))

        btn_add_files = ttk.Button(
            input_buttons,
            text="+ Adicionar arquivos",
            command=self.add_files
        )
        btn_add_files.pack(side=tk.LEFT)

        btn_remove = ttk.Button(
            input_buttons,
            text="- Remover selecionado",
            command=self.remove_file
        )
        btn_remove.pack(side=tk.LEFT, padx=(6, 0))

        list_frame = ttk.Frame(input_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox = tk.Listbox(
            list_frame,
            yscrollcommand=scrollbar.set,
            height=4,
            font=("Helvetica", 10)
        )
        self.file_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar.config(command=self.file_listbox.yview)

        self.conversion_thread = None
        self.is_converting = False

    def add_files(self):
        """Adiciona arquivos AVI à lista."""
        files = filedialog.askopenfilenames(
            title="Selecionar Vídeos AVI",
            filetypes=[("AVI files", "*.avi"), ("All files", "*.*")]
        )
        for file in files:
            if file not in self.selected_files:
                self.selected_files.append(file)
                self.file_listbox.insert(tk.END, Path(file).name)

    def remove_file(self):
        """Remove arquivo selecionado da lista."""
        selection = self.file_listbox.curselection()
        if selection:
            idx = selection[0]
            self.file_listbox.delete(idx)
            del self.selected_files[idx]

    def select_output_dir(self):
        """Seleciona a pasta de destino."""
        folder = filedialog.askdirectory(title="Selecionar Pasta de Destino")
        if folder:
            self.output_dir = folder
            self.output_label.config(text=folder)

    def start_conversion(self):
        """Inicia a conversão em thread separada."""
        if not self.selected_files:
            messagebox.showwarning("Aviso", "Selecione pelo menos um arquivo AVI.")
            return

        if not self.output_dir:
            messagebox.showwarning("Aviso", "Selecione uma pasta de destino.")
            return

        self.is_converting = True
        self.btn_convert.config(state="disabled")
        self.progress_var.set(0)
        self.status_label.config(text="Convertendo...", foreground="orange")

        self.conversion_thread = threading.Thread(target=self.convert_files, daemon=True)
        self.conversion_thread.start()

    def convert_files(self):
        """Realiza a conversão dos arquivos."""
        total_files = len(self.selected_files)
        font = Path(__file__).resolve().parent / "fonts" / "sonycam-original.ttf"

        for idx, file in enumerate(self.selected_files):
            try:
                source = Path(file).resolve()
                output = (Path(self.output_dir) / (source.stem + ".avi")).resolve()

                if not source.is_file():
                    raise VideoError(f"Arquivo de entrada não encontrado: {source}")
                if output.suffix.lower() != ".avi":
                    raise VideoError("A saída deve ter extensão .avi.")
                if source == output or output.exists():
                    raise VideoError(f"A saída já existe ou coincide com a entrada: {output}")
                if not font.is_file():
                    raise VideoError(f"Fonte não encontrada: {font}")

                for tool in ("ffmpeg", "ffprobe"):
                    if not shutil.which(tool):
                        raise VideoError(f"{tool} não encontrado no PATH.")

                self.update_status(f"Processando {source.name}...")

                fps = probe(source, creationflags=NO_CONSOLE)

                with tempfile.TemporaryDirectory(prefix="sony-date-dv-") as directory:
                    temp = Path(directory)
                    (temp / "fonts").mkdir()
                    shutil.copy2(font, temp / "fonts" / font.name)

                    self.update_status(f"Lendo datas dos quadros DV: {source.name}...")
                    frames, missing = extract_subtitles(
                        source, fps, temp / "datas.ass", creationflags=NO_CONSOLE
                    )

                    self.update_status(f"Gerando vídeo: {source.name}...")
                    subprocess.run(
                        ["ffmpeg", "-hide_banner", "-nostdin", "-n", "-i", str(source),
                         "-map", "0:v:0", "-map", "0:a?", "-vf",
                         "bwdif=mode=send_frame:parity=auto:deint=interlaced,ass=datas.ass:fontsdir=fonts",
                         "-c:v", "dvvideo", "-pix_fmt", "yuv420p" if fps == 25 else "yuv411p",
                         "-c:a", "pcm_s16le",
                         str(output)],
                        cwd=temp, check=True, capture_output=True, creationflags=NO_CONSOLE,
                    )

                progress = ((idx + 1) / total_files) * 100
                self.progress_var.set(progress)
                self.update_status(f"✓ Concluído: {source.name}")

            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror(
                    "Erro na Conversão",
                    f"Erro ao converter {Path(file).name}:\n{str(e)}"
                ))
                self.is_converting = False
                self.btn_convert.config(state="normal")
                self.status_label.config(text="Erro!", foreground="red")
                return

        self.is_converting = False
        self.progress_var.set(100)
        self.status_label.config(text="Conversão concluída com sucesso!", foreground="green")
        self.btn_convert.config(state="normal")
        self.root.after(0, lambda: messagebox.showinfo(
            "Sucesso",
            f"{total_files} arquivo(s) convertido(s) com sucesso!"
        ))

    def update_status(self, message):
        """Atualiza a mensagem de status de forma thread-safe."""
        self.root.after(0, lambda: self.status_label.config(text=message))


def main_gui():
    root = tk.Tk()
    app = DVConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main_gui()
