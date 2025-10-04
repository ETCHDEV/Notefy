# server.py

from flask import Flask, request, jsonify, send_from_directory
import os
import time
from datetime import datetime, timedelta, timezone
import librosa
import numpy as np
from pydub import AudioSegment
import joblib
import music21
import subprocess
import mysql.connector
import bcrypt
import jwt
from functools import wraps

# --- Flask App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-very-secret-and-random-string'

# --- Configuration ---
MODEL_PATH = 'models/notefy_instrument_classifier_high_accuracy.joblib'
UPLOADS_DIR = 'uploads'
OUTPUTS_DIR = 'outputs'
MUSESCORE_EXECUTABLE_PATH = '/Applications/MuseScore 4.app/Contents/MacOS/mscore'

# --- Database Configuration ---
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'notefy_db'
}

# Create necessary directories
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# Load the model once at startup
try:
    instrument_model = joblib.load(MODEL_PATH)
except FileNotFoundError:
    instrument_model = None

# --- Database Connection Helper ---
def get_db_connection():
    conn = mysql.connector.connect(**db_config)
    return conn

# --- JWT Token Decorator ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('x-access-token')
        if not token: return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user_id = data['user_id']
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(current_user_id, *args, **kwargs)
    return decorated

# --- CORE NOTEFY PROCESSING FUNCTIONS ---
def remove_vocals(input_path, output_path):
    stereo_audio = AudioSegment.from_file(input_path)
    mono_audio = stereo_audio.set_channels(1)
    mono_audio.export(output_path, format="wav")
    return output_path

def detect_instruments(audio_path, model):
    y, sr = librosa.load(audio_path, mono=True)
    detected_instruments = set()
    for i in range(0, len(y), sr):
        chunk = y[i:i + sr]
        if len(chunk) < sr / 2: continue
        mfcc = np.mean(librosa.feature.mfcc(y=chunk, sr=sr, n_mfcc=40).T, axis=0)
        zcr = np.mean(librosa.feature.zero_crossing_rate(y=chunk).T, axis=0)
        spec_cent = np.mean(librosa.feature.spectral_centroid(y=chunk, sr=sr).T, axis=0)
        features = np.hstack([mfcc, zcr, spec_cent])
        prediction = model.predict([features])
        detected_instruments.add(prediction[0])
    return list(detected_instruments) if detected_instruments else ['unknown']
    
def detect_pitch(y, sr):
    f0, _, _ = librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'))
    return np.nan_to_num(f0)

def generate_sheet_music(pitches, sr, output_base_name, instruments_to_include):
    times = librosa.times_like(pitches, sr=sr)
    score = music21.stream.Score()
    part = music21.stream.Part()
    part.partName = ', '.join(instruments_to_include)
    current_note_pitch, current_note_duration = None, 0

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

    if not part.notes: return None, None
    score.insert(0, part)
    xml_path = os.path.join(OUTPUTS_DIR, f"{output_base_name}.musicxml")
    score.write('musicxml', fp=xml_path)
    return score, xml_path
    
def export_to_pdf_with_musescore(xml_path):
    if not os.path.exists(MUSESCORE_EXECUTABLE_PATH) or not os.path.exists(xml_path): return None
    pdf_path = xml_path.replace('.musicxml', '.pdf')
    command = [MUSESCORE_EXECUTABLE_PATH, '-o', pdf_path, xml_path]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return pdf_path

def sheet_to_midi(sheet_music_path):
    score = music21.converter.parse(sheet_music_path)
    base_name = os.path.splitext(os.path.basename(sheet_music_path))[0]
    midi_path = os.path.join(OUTPUTS_DIR, f"{base_name}.mid")
    score.write('midi', fp=midi_path)
    return midi_path

# --- API Endpoints ---
@app.route('/api/signup', methods=['POST'])
def api_signup():
    data = request.json
    username, email, password = data.get('username'), data.get('email'), data.get('password')
    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)", (username, email, hashed_password))
        conn.commit()
        return jsonify({"success": True, "message": "Signup successful!"})
    except mysql.connector.Error as err:
        return jsonify({"success": False, "message": str(err)}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username, password = data.get('username'), data.get('password')
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        token = jwt.encode({
            'user_id': user['id'],
            'exp': datetime.now(timezone.utc) + timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({"success": True, "message": "Login successful!", "token": token})
    else:
        return jsonify({"success": False, "message": "Invalid username or password"}), 401

@app.route('/api/profile', methods=['GET'])
@token_required
def api_get_profile(current_user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT username, email, join_date FROM users WHERE id = %s", (current_user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if user:
        return jsonify(user)
    return jsonify({"message": "User not found"}), 404
    
@app.route('/api/profile', methods=['POST'])
@token_required
def api_update_profile(current_user_id):
    data = request.json
    new_username, new_email = data.get('username'), data.get('email')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET username = %s, email = %s WHERE id = %s", (new_username, new_email, current_user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": "Profile updated successfully"})

@app.route('/api/history', methods=['GET'])
@token_required
def get_history(current_user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, original_filename, output_pdf_path, output_midi_path, transcription_date FROM transcriptions WHERE user_id = %s ORDER BY transcription_date DESC",
        (current_user_id,)
    )
    history = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(history)

@app.route('/api/history/rename', methods=['POST'])
@token_required
def rename_history(current_user_id):
    data = request.json
    transcription_id, new_name = data.get('id'), data.get('newName')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE transcriptions SET original_filename = %s WHERE id = %s AND user_id = %s", (new_name, transcription_id, current_user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'message': 'History item renamed.'})

@app.route('/api/settings', methods=['GET'])
@token_required
def get_settings(current_user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT pitch_offset FROM user_settings WHERE user_id = %s", (current_user_id,))
    settings = cursor.fetchone()
    cursor.close()
    conn.close()
    if settings:
        return jsonify(settings)
    return jsonify({'pitch_offset': 0})

@app.route('/api/settings', methods=['POST'])
@token_required
def save_settings(current_user_id):
    data = request.json
    pitch_offset = data.get('pitch_offset')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_settings (user_id, pitch_offset) VALUES (%s, %s) ON DUPLICATE KEY UPDATE pitch_offset = %s",
        (current_user_id, pitch_offset, pitch_offset)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'message': 'Settings saved.'})

@app.route('/api/detect-instruments', methods=['POST'])
@token_required
def api_detect_instruments(current_user_id):
    if 'audio_file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['audio_file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    temp_filename = f"upload_{current_user_id}_{int(time.time())}.mp3"
    mp3_path = os.path.join(UPLOADS_DIR, temp_filename)
    file.save(mp3_path)
    
    instrumental_path = os.path.join(UPLOADS_DIR, f"instrumental_{os.path.splitext(temp_filename)[0]}.wav")
    remove_vocals(mp3_path, instrumental_path)
    instruments = detect_instruments(instrumental_path, instrument_model)
    
    return jsonify({"instruments": instruments, "instrumental_path": instrumental_path})

@app.route('/api/generate-sheet', methods=['POST'])
@token_required
def api_generate_sheet(current_user_id):
    data = request.json
    instrumental_path = data.get('instrumental_path')
    instruments_to_generate = data.get('instruments_to_generate')
    original_filename = os.path.basename(instrumental_path).replace('instrumental_', '').replace('.wav', '.mp3')
    
    y, sr = librosa.load(instrumental_path)
    pitches = detect_pitch(y, sr)
    
    output_files, saved_pdf_path, saved_midi_path = [], None, None
    base_name = os.path.splitext(os.path.basename(instrumental_path).replace('instrumental_', ''))[0]

    for instrument_list in instruments_to_generate:
        file_base_name = f"{base_name}_{'_'.join(instrument_list)}" if len(instrument_list) == 1 else base_name
        score, xml_path = generate_sheet_music(pitches, sr, file_base_name, instrument_list)
        if xml_path:
            pdf_path = export_to_pdf_with_musescore(xml_path)
            if pdf_path:
                output_files.append(os.path.basename(pdf_path))
                saved_pdf_path = os.path.basename(pdf_path)
            if data.get('generate_midi'):
                midi_path = sheet_to_midi(xml_path)
                if midi_path:
                    output_files.append(os.path.basename(midi_path))
                    saved_midi_path = os.path.basename(midi_path)
    
    if saved_pdf_path or saved_midi_path:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO transcriptions (user_id, original_filename, output_pdf_path, output_midi_path) VALUES (%s, %s, %s, %s)",
            (current_user_id, original_filename, saved_pdf_path, saved_midi_path)
        )
        conn.commit()
        cursor.close()
        conn.close()

    return jsonify({"output_files": output_files})

# --- Static File Serving ---
@app.route('/')
def index():
    return send_from_directory('.', 'newlogin.html')

@app.route('/<path:path>')
def send_static(path):
    return send_from_directory('.', path)

@app.route('/outputs/<filename>')
def serve_output_file(filename):
    return send_from_directory(OUTPUTS_DIR, filename, as_attachment=True)

# --- Run the Server ---
if __name__ == '__main__':
    if instrument_model is None:
        print("Could not start server because the ML model is not loaded.")
    else:
        print("Starting Notefy server at http://127.0.0.1:5000")
        app.run(host='0.0.0.0', port=5000, debug=True)