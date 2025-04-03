import speech_recognition as sr
import whisper
import numpy as np
import io
import soundfile as sf
import torch
import os
import yfinance as yf
import pyautogui
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.mime.text import MIMEText
import base64
import spacy
import requests
import tkinter as tk
from tkinter import scrolledtext
import threading
import pyttsx3

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# GPU Check
print(f"GPU Available: {torch.cuda.is_available()}")
model = whisper.load_model("base.en", device="cuda" if torch.cuda.is_available() else "cpu")

# OAuth Setup (Gmail & Calendar)
SCOPES = ['https://www.googleapis.com/auth/gmail.send', 'https://www.googleapis.com/auth/calendar']
creds = None
if os.path.exists('token.json'):
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
if not creds or not creds.valid:
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
gmail_service = build('gmail', 'v1', credentials=creds)
calendar_service = build('calendar', 'v3', credentials=creds)

def send_email(to_email, subject, body):
    msg = MIMEText(body)
    msg['to'] = to_email
    msg['subject'] = subject
    msg['from'] = 'example@example.com' # Enter your email here
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    message = {'raw': raw}
    gmail_service.users().messages().send(userId='me', body=message).execute()
    print(f"Email sent to {to_email}")

def check_stock(ticker="RELIANCE.NS"):
    stock = yf.Ticker(ticker).history(period="1d")["Close"].iloc[-1]
    return f"{ticker}: ₹{stock:.2f}"

def get_weather(city="Mumbai"):
    url = f"https://api.open-meteo.com/v1/forecast?latitude=19.0760&longitude=72.8777¤t_weather=true"
    if city.lower() != "mumbai":
        url = f"https://api.open-meteo.com/v1/forecast?latitude={get_lat_lon(city)[0]}&longitude={get_lat_lon(city)[1]}¤t_weather=true"
    response = requests.get(url)
    data = response.json()
    if data.get("current_weather"):
        temp = data['current_weather']['temperature']
        weather_code = data['current_weather']['weathercode']
        return f"Weather in {city}: {temp}°C, {weather_code_to_desc(weather_code)}"
    return "Weather data unavailable"

def weather_code_to_desc(code):
    codes = {0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast"}
    return codes.get(code, "Unknown")

def get_lat_lon(city):
    city_coords = {"delhi": (28.7041, 77.1025), "mumbai": (19.0760, 72.8777)}
    return city_coords.get(city.lower(), (19.0760, 72.8777))

def speak(text):
    engine = pyttsx3.init()
    engine.say(text)
    engine.runAndWait()

def add_calendar_event(summary, start_time, end_time):
    event = {
        'summary': summary,
        'start': {'dateTime': start_time, 'timeZone': 'Asia/Kolkata'},
        'end': {'dateTime': end_time, 'timeZone': 'Asia/Kolkata'},
    }
    calendar_service.events().insert(calendarId='primary', body=event).execute()
    print(f"Event '{summary}' added to calendar")

# Browser Interface
def start_browser_interface():
    root = tk.Tk()
    root.title("Jarvis Browser")
    text_area = scrolledtext.ScrolledText(root, width=80, height=20)
    text_area.pack(padx=10, pady=10)

    def load_url(url):
        try:
            response = requests.get(url)
            text_area.delete(1.0, tk.END)
            text_area.insert(tk.END, response.text)
        except Exception as e:
            text_area.insert(tk.END, f"Error: {e}")

    def run_browser():
        root.mainloop()
        return search_web

    return run_browser()

# NLP Parsing with spaCy
def parse_command(text):
    doc = nlp(text.lower())
    intents = {
        "email": ["send", "email"],
        "stock": ["check", "stock"],
        "weather": ["get", "weather"],
        "calendar": ["add", "event"],
        "app": ["open", "type"],
        "search": ["search", "web"]
    }
    for intent, keywords in intents.items():
        if any(token.lemma_ in keywords for token in doc):
            entities = {}
            if intent == "email":
                for ent in doc.ents:
                    if ent.label_ == "PERSON":
                        entities["to"] = ent.text + "@example.com"
                    if "about" in text:
                        entities["body"] = text.split("about")[-1].strip()
                if not entities.get("to"):
                    entities["to"] = "recipient@example.com" # Enter recipient's email
            elif intent == "weather":
                entities["city"] = next((ent.text for ent in doc.ents if ent.label_ == "GPE"), "Mumbai")
            elif intent == "calendar" and any("at" in token.text for token in doc):
                entities["time"] = next((token.text for token in doc if token.text == "at" and doc[token.i + 1].like_num), "2025-03-11T12:00:00")
            return intent, entities
    return None, {}

# Main Loop
def main():
    r = sr.Recognizer()
    browser_thread = threading.Thread(target=start_browser_interface, daemon=True)
    browser_thread.start()

    while True:
        with sr.Microphone(sample_rate=16000) as source:
            print("Say 'Jarvis' and a command...")
            r.adjust_for_ambient_noise(source, duration=1)
            audio = r.listen(source, timeout=5, phrase_time_limit=5)
            audio_bytes = audio.get_wav_data()
            audio_data, _ = sf.read(io.BytesIO(audio_bytes))
            audio_data = audio_data.astype(np.float32)
            result = model.transcribe(audio_data)
            text = result["text"].lower()
            print(f"Heard: '{text}'")

            if "jarvis" in text:
                print("Jarvis activated—let’s roll!")
                intent, entities = parse_command(text)
                if intent == "email":
                    to_email = entities.get("to", "recipient@example.com") # Enter recipient's email
                    body = entities.get("body", "Default message from Jarvis")
                    send_email(to_email, "Custom Email", body)
                elif intent == "stock":
                    print(check_stock())
                elif intent == "weather":
                    city = entities.get("city", "Mumbai")
                    print(get_weather(city))
                elif intent == "calendar":
                    event_time = entities.get("time", "2025-03-11T12:00:00")
                    add_calendar_event("New Event", event_time, f"{event_time[:-8]}13:00:00")
                elif intent == "app":
                    if "notepad" in text:
                        os.system("notepad")
                        print("Opening Notepad...")
                    elif "chrome" in text:
                        os.system("start chrome")
                        print("Opening Chrome...")
                    elif "type hello" in text:
                        pyautogui.typewrite("Hello from Jarvis!")
                        pyautogui.press("enter")
                        print("Typed 'Hello from Jarvis!'")
                elif intent == "search":
                    query = text.split("search")[-1].strip() if "search" in text else "default"
                    search_web_func = start_browser_interface()
                    search_web_func("your_query")
                elif "exit" in text:
                    print("Shutting down...")
                    break
                speak(f"Command {intent} executed if recognized.")
            else:
                speak(f"No 'Jarvis' detected. Try again!")
                print(f"No 'Jarvis' detected—try again!")
   
        time.sleep(1)

if __name__ == "__main__":
    main()