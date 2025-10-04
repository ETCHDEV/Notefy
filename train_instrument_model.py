# train_instrument_model.py

import librosa
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
import joblib
import os
from midi2audio import FluidSynth

# --- Configuration for HIGH ACCURACY training ---
IRMAS_PATH = 'datasets/IRMAS-TrainingData/Training'
LMD_PATH = 'datasets/LMD-Clean'
SOUNDFONT_PATH = 'GeneralUser GS v1.471.sf2'
TEMP_WAV_OUTPUT = 'temp_synth.wav'
MODEL_OUTPUT_PATH = 'models/notefy_instrument_classifier_high_accuracy.joblib'

def extract_features(file_path):
    try:
        y, sr = librosa.load(file_path, mono=True, duration=5)
        mfcc = np.mean(librosa.feature.mfcc(y=y, sr=sr, n_mfcc=40).T, axis=0)
        zcr = np.mean(librosa.feature.zero_crossing_rate(y).T, axis=0)
        spec_cent = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr).T, axis=0)
        chroma = np.mean(librosa.feature.chroma_stft(y=y, sr=sr).T, axis=0)
        rolloff = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr).T, axis=0)
        return np.hstack([mfcc, zcr, spec_cent, chroma, rolloff])
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

def train_model():
    all_features = []
    print("--- Processing FULL IRMAS Dataset ---")
    if os.path.exists(IRMAS_PATH):
        for instrument_folder in os.listdir(IRMAS_PATH):
            instrument_path = os.path.join(IRMAS_PATH, instrument_folder)
            if os.path.isdir(instrument_path):
                instrument_label = instrument_folder
                print(f"Processing instrument: {instrument_label}")
                for filename in os.listdir(instrument_path):
                    if filename.endswith('.wav'):
                        file_path = os.path.join(instrument_path, filename)
                        features = extract_features(file_path)
                        if features is not None:
                            all_features.append([*features, instrument_label])
    else:
        print(f"Warning: IRMAS path not found at '{IRMAS_PATH}'.")

    print("\n--- Processing FULL LMD-Clean Dataset ---")
    if os.path.exists(LMD_PATH) and os.path.exists(SOUNDFONT_PATH):
        fs = FluidSynth(SOUNDFONT_PATH)
        processed_count = 0
        total_files = sum(len(files) for _, _, files in os.walk(LMD_PATH) if any(f.endswith('.mid') for f in files))
        print(f"Found {total_files} MIDI files to process...")
        
        for root, _, files in os.walk(LMD_PATH):
            for filename in files:
                if filename.endswith(('.mid', '.midi')):
                    file_path = os.path.join(root, filename)
                    try:
                        fs.midi_to_audio(file_path, TEMP_WAV_OUTPUT)
                        features = extract_features(TEMP_WAV_OUTPUT)
                        if features is not None:
                            all_features.append([*features, 'synth_midi'])
                        processed_count += 1
                        if processed_count % 100 == 0:
                            print(f"Processed {processed_count}/{total_files} MIDI files...")
                    except Exception as e:
                        print(f"Could not process MIDI file {filename}: {e}")
    else:
        print(f"Warning: LMD path or SoundFont not found.")
    
    if os.path.exists(TEMP_WAV_OUTPUT): os.remove(TEMP_WAV_OUTPUT)
    if not all_features:
        print("No features were extracted. Exiting.")
        return

    print("\n--- Preparing and Balancing the Dataset ---")
    df = pd.DataFrame(all_features)
    df.rename(columns={df.columns[-1]: 'instrument'}, inplace=True)

    real_instrument_df = df[df['instrument'] != 'synth_midi']
    midi_df = df[df['instrument'] == 'synth_midi']
    
    avg_real_samples = int(real_instrument_df['instrument'].value_counts().mean())
    if len(midi_df) > avg_real_samples:
        midi_df_sampled = midi_df.sample(n=avg_real_samples, random_state=42)
        df_balanced = pd.concat([real_instrument_df, midi_df_sampled])
    else:
        df_balanced = df

    print("Final class distribution:\n", df_balanced['instrument'].value_counts())

    X = df_balanced.drop('instrument', axis=1)
    y = df_balanced['instrument']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    print("\n--- Training High-Accuracy Random Forest Model ---")
    model = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    print("Training complete.")

    y_pred = model.predict(X_test)
    print(f"Final Model Accuracy: {accuracy_score(y_test, y_pred):.2f}")

    joblib.dump(model, MODEL_OUTPUT_PATH)
    print(f"High-accuracy model saved to {MODEL_OUTPUT_PATH}")

if __name__ == '__main__':
    train_model()