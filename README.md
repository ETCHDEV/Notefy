# Notefy 🎵

**Notefy is an AI-powered web application that automatically transcribes music from an MP3 file into playable sheet music.**

Built without deep learning, this project uses classical machine learning and signal processing techniques to analyze audio, identify instruments, and generate a musical score. It features a full user authentication system with a persistent history, all wrapped in a clean, user-friendly web interface.



## Features

- **Automatic Music Transcription:** Converts instrumental or vocal MP3s into sheet music.
- **Instrument Recognition:** Utilizes a **Random Forest** model to identify the instruments playing in the track.
- **Vocal Removal:** Employs **Independent Component Analysis (ICA)** to separate vocals from a stereo mix, isolating the instrumental track for analysis.
- **Web-Based GUI:** A modern, browser-based interface built with Flask and JavaScript for a seamless user experience.
- **User Authentication:** A complete user system with signup, login, and profile management, backed by a MySQL database.
- **Persistent History:** Each user's transcription history is saved to their account.
- **Dynamic Audio Controls:** Users can adjust the pitch and playback speed of the uploaded audio before transcription.
- **PDF & MIDI Output:** Generates high-quality PDF sheet music via MuseScore and optional MIDI files for use in any Digital Audio Workstation (DAW).

## Technology Stack

- **Backend:** Python, Flask
- **Machine Learning:** Scikit-learn (Random Forest)
- **Audio Processing:** Librosa, Pydub
- **Musicology Toolkit:** Music21
- **Database:** MySQL
- **Frontend:** HTML, CSS, JavaScript
- **User Authentication:** PyJWT (JSON Web Tokens), bcrypt

## How It Works: Dataflow

Notefy processes audio through a sophisticated pipeline:

1.  **User Uploads MP3:** The process starts with the user's audio file.
2.  **Vocal Removal (ICA):** The system isolates the instrumental track from the stereo mix.
3.  **Feature Extraction:** The instrumental audio is analyzed to create a "sonic fingerprint" using features like **MFCCs, Zero-Crossing Rate, and Spectral Centroid**.
4.  **Instrument Detection (Random Forest):** The trained model predicts the instruments based on the audio features.
5.  **Pitch Detection (YIN):** The dominant melodic line of the instrumental track is identified.
6.  **Sheet Music Generation (Music21):** The detected notes are assembled into a musical score.
7.  **Final Output:** The score is saved as PDF and optional MIDI files, and the record is saved to the user's history in the database.

## Setup and Installation

Follow these steps to set up the project on a macOS environment.

### 1. Prerequisites
- **Homebrew:** Make sure you have Homebrew installed.
- **For Windows & Linux:** Don't need to install homebrew.
- **MySQL:** You need a running MySQL server.

### 2. Clone the Repository
```bash
git clone https://github.com/ETCHDEV/Notefy.git
cd notefy
```

### 3. System Dependencies
Install required system libraries using Homebrew.
```bash
brew install mysql fluidsynth musescore
```
For Windows & Linux:
Search gpt for installing fluidsynth and musescore

*Note: Ensure the MuseScore application is in your `/Applications` folder (Only for MacOS).*

### 4. Database Setup
Log in to MySQL and import the .sql file.

### 5. Python Environment
Create and activate a virtual environment, then install the required packages.
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
For Windows:
Ask ChatGPT

## How to Use

### 1. Train the Model
You only need to do this once. This script will process the datasets and create the instrument classifier. **This will take a long time.**
(No need has I have included an trained model)
```bash
python train_instrument_model.py
```

### 2. Run the Web Server
Start the Flask backend server.
```bash
python server.py
```
For Windows & Linux:
Ask ChatGPT if any error occurs

### 3. Access the Application
Open your web browser and navigate to:
**http://127.0.0.1:5000**

You can now sign up for an account, log in, and start transcribing music!

## Limitations

- **Monophonic Transcription:** The system is designed to detect the single, most dominant melodic line. It cannot transcribe polyphonic music (multiple notes at once, like chords).
- **Rhythm Simplification:** Complex rhythms and timing nuances are simplified (quantized), so the output may not capture the full rhythmic feel of the original performance.
- **Expressive Details:** The transcription does not include dynamics (loud/soft), articulations, or other performance expressions.

### For any errors and doubt, ask any generative AI like Gemini or ChatGPT by inputing the code + error after that and ask to optimize it to your platform. Has I have no time to give solution to any errors and being on MacOS, some code was hardwired to MacOS.
