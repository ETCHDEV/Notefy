# gui_app.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import threading
import queue
import os
import librosa
import numpy as np
from pydub import AudioSegment
import joblib
import music21
import subprocess

# --- Configuration ---
MODEL_PATH = 'models/notefy_instrument_classifier.joblib' # Matches training script output
UPLOADS_DIR = 'uploads'
OUTPUTS_DIR = 'outputs'
MUSESCORE_EXECUTABLE_PATH = '/Applications/MuseScore 4.app/Contents/MacOS/mscore'

# --- Core Processing Logic (Adapted for GUI) ---
def export_to_pdf_with_musescore(xml_path, status_callback):
    if not os.path.exists(MUSESCORE_EXECUTABLE_PATH):
        status_callback("Error: MuseScore executable not found. Cannot generate PDF.")
        return
    if not os.path.exists(xml_path): return

    pdf_path = xml_path.replace('.musicxml', '.pdf')
    status_callback(f"Generating PDF: {os.path.basename(pdf_path)}...")
    try:
        command = [MUSESCORE_EXECUTABLE_PATH, '-o', pdf_path, xml_path]
        subprocess.run(command, check=True, capture_output=True, text=True)
        status_callback("PDF generated successfully.")
    except Exception as e:
        status_callback(f"MuseScore PDF generation failed: {e}")

def remove_vocals(input_path, output_path, status_callback):
    status_callback("Removing vocals...")
    stereo_audio = AudioSegment.from_file(input_path)
    mono_audio = stereo_audio.set_channels(1)
    mono_audio.export(output_path, format="wav")
    status_callback("Instrumental track created.")
    return output_path

def detect_instruments(audio_path, model, status_callback):
    status_callback("Detecting instruments...")
    y, sr = librosa.load(audio_path, mono=True)
    detected_instruments = set()
    
    for i in range(0, len(y), sr):
        chunk = y[i:i + sr]
        if len(chunk) < sr / 2: continue
        
        mfcc = np.mean(librosa.feature.mfcc(y=y, sr=sr, n_mfcc=40).T, axis=0)
        zcr = np.mean(librosa.feature.zero_crossing_rate(y).T, axis=0)
        spec_cent = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr).T, axis=0)
        features = np.hstack([mfcc, zcr, spec_cent])

        prediction = model.predict([features])
        detected_instruments.add(prediction[0])
        
    results = list(detected_instruments) if detected_instruments else ['unknown']
    status_callback(f"Detected: {', '.join(results)}")
    return results

def detect_pitch(y, sr, status_callback):
    status_callback("Detecting pitches...")
    f0, _, _ = librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'))
    f0 = np.nan_to_num(f0)
    return f0

def generate_sheet_music(pitches, sr, output_base_name, instruments_to_include, status_callback):
    status_callback(f"Generating sheet for {', '.join(instruments_to_include)}...")
    times = librosa.times_like(pitches, sr=sr)
    score = music21.stream.Score()
    part = music21.stream.Part()
    part.partName = ', '.join(instruments_to_include)

    current_note_pitch = None
    current_note_duration = 0

    def add_note_to_part(pitch, duration_frames):
        if pitch is None: return
        time_per_frame = times[1] - times[0] if len(times) > 1 else 0.02
        duration_in_quarters = duration_frames * time_per_frame
        quantized_duration = round(duration_in_quarters * 4) / 4.0
        if quantized_duration > 0:
            new_note = music21.note.Note(pitch.nameWithOctave)
            new_note.duration.quarterLength = quantized_duration
            part.append(new_note)

    for i in range(len(pitches)):
        freq = pitches[i]
        if freq > 0:
            pitch = music21.pitch.Pitch()
            pitch.frequency = freq
            if current_note_pitch and pitch.nameWithOctave == current_note_pitch.nameWithOctave:
                current_note_duration += 1
            else:
                add_note_to_part(current_note_pitch, current_note_duration)
                current_note_pitch, current_note_duration = pitch, 1
        else:
            add_note_to_part(current_note_pitch, current_note_duration)
            current_note_pitch, current_note_duration = None, 0
    add_note_to_part(current_note_pitch, current_note_duration)

    if not part.notes:
        status_callback("No notes generated.")
        return None, None

    score.insert(0, part)
    xml_path = os.path.join(OUTPUTS_DIR, f"{output_base_name}.musicxml")
    score.write('musicxml', fp=xml_path)
    status_callback(f"Saved: {os.path.basename(xml_path)}")
    return score, xml_path

def sheet_to_midi(sheet_music_path, status_callback):
    if not os.path.exists(sheet_music_path):
        status_callback(f"Error: File not found '{sheet_music_path}'")
        return
    try:
        status_callback(f"Loading '{os.path.basename(sheet_music_path)}'...")
        score = music21.converter.parse(sheet_music_path)
        base_name = os.path.splitext(os.path.basename(sheet_music_path))[0]
        midi_path = os.path.join(OUTPUTS_DIR, f"{base_name}.mid")
        score.write('midi', fp=midi_path)
        status_callback(f"MIDI file saved: {os.path.basename(midi_path)}")
    except Exception as e:
        status_callback(f"MIDI conversion failed: {e}")

# --- GUI Application ---
class NotefyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Notefy")
        self.root.geometry("500x450")

        try:
            self.instrument_model = joblib.load(MODEL_PATH)
        except FileNotFoundError:
            messagebox.showerror("Error", f"Model file not found at '{MODEL_PATH}'.\nPlease run train_instrument_model.py first.")
            self.root.destroy()
            return
        
        style = ttk.Style()
        style.configure("TButton", padding=6, relief="flat", font=('Helvetica', 12))
        style.configure("TLabel", padding=5, font=('Helvetica', 11))
        style.configure("Header.TLabel", font=('Helvetica', 16, 'bold'))

        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Notefy", style="Header.TLabel").pack(pady=(0, 20))
        ttk.Button(main_frame, text="Convert MP3 to Sheet Music", command=self.select_mp3_and_process).pack(fill=tk.X, pady=5)
        ttk.Button(main_frame, text="Convert Sheet Music to MIDI", command=self.convert_sheet_to_midi).pack(fill=tk.X, pady=5)

        status_frame = ttk.LabelFrame(main_frame, text="Status", padding="10")
        status_frame.pack(fill=tk.BOTH, expand=True, pady=(20, 0))
        self.status_text = tk.Text(status_frame, height=10, state="disabled", wrap="word", font=('Helvetica', 10))
        self.status_text.pack(fill=tk.BOTH, expand=True)

        self.queue = queue.Queue()
        self.root.after(100, self.process_queue)

    def log_status(self, message):
        self.queue.put(message)

    def process_queue(self):
        try:
            message = self.queue.get_nowait()
            self.status_text.config(state="normal")
            self.status_text.insert(tk.END, message + "\n")
            self.status_text.see(tk.END)
            self.status_text.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self.process_queue)

    def select_mp3_and_process(self):
        file_path = filedialog.askopenfilename(title="Select an MP3 File", filetypes=[("MP3 files", "*.mp3")])
        if not file_path: return
        
        self.status_text.config(state="normal")
        self.status_text.delete(1.0, tk.END)
        self.status_text.config(state="disabled")
        self.log_status(f"Selected: {os.path.basename(file_path)}")
        
        thread = threading.Thread(target=self.process_mp3_worker, args=(file_path,))
        thread.daemon = True
        thread.start()

    def process_mp3_worker(self, file_path):
        try:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            instrumental_path = os.path.join(UPLOADS_DIR, f"instrumental_{base_name}.wav")
            remove_vocals(file_path, instrumental_path, self.log_status)
            detected_instruments = detect_instruments(instrumental_path, self.instrument_model, self.log_status)
            y, sr = librosa.load(instrumental_path)
            pitches = detect_pitch(y, sr, self.log_status)
            self.root.after(0, self.ask_sheet_music_choice, pitches, sr, base_name, detected_instruments)
        except Exception as e:
            self.log_status(f"An error occurred: {e}")

    def ask_sheet_music_choice(self, pitches, sr, base_name, detected_instruments):
        choice_window = tk.Toplevel(self.root)
        choice_window.title("Sheet Music Options")
        
        ttk.Label(choice_window, text="How would you like to generate the sheet music?").pack(padx=20, pady=10)
        
        def on_choice(choice):
            choice_window.destroy()
            thread = threading.Thread(target=self.generate_chosen_sheets, args=(choice, pitches, sr, base_name, detected_instruments))
            thread.daemon = True
            thread.start()

        ttk.Button(choice_window, text="Combined for All Instruments", command=lambda: on_choice('combined')).pack(fill=tk.X, padx=20, pady=5)
        ttk.Button(choice_window, text="Separate for Individual Instruments", command=lambda: on_choice('individual')).pack(fill=tk.X, padx=20, pady=5)
        
    def generate_chosen_sheets(self, choice, pitches, sr, base_name, detected_instruments):
        try:
            if choice == 'combined':
                score, xml_path = generate_sheet_music(pitches, sr, base_name, detected_instruments, self.log_status)
                if xml_path:
                    export_to_pdf_with_musescore(xml_path, self.log_status)
                    if messagebox.askyesno("MIDI Option", "Also convert this sheet to a MIDI file?"):
                        sheet_to_midi(xml_path, self.log_status)
            
            elif choice == 'individual':
                self.log_status("Reminder: Each sheet will have the same dominant melody.")
                for instrument in detected_instruments:
                    inst_base_name = f"{base_name}_{instrument}"
                    score, xml_path = generate_sheet_music(pitches, sr, inst_base_name, [instrument], self.log_status)
                    if xml_path:
                        export_to_pdf_with_musescore(xml_path, self.log_status)
                        if messagebox.askyesno("MIDI Option", f"Convert sheet for '{instrument}' to MIDI?"):
                            sheet_to_midi(xml_path, self.log_status)
            self.log_status("\nProcessing finished!")
        except Exception as e:
            self.log_status(f"An error occurred during generation: {e}")

    def convert_sheet_to_midi(self):
        file_path = filedialog.askopenfilename(title="Select a Sheet Music File", filetypes=[("MusicXML", "*.musicxml"), ("XML", "*.xml")])
        if not file_path: return
        
        self.status_text.config(state="normal")
        self.status_text.delete(1.0, tk.END)
        self.status_text.config(state="disabled")
        sheet_to_midi(file_path, self.log_status)


if __name__ == "__main__":
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    root = tk.Tk()
    app = NotefyApp(root)
    root.mainloop()