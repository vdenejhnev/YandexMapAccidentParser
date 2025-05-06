from flask import Flask, render_template, request, redirect
import json
import os
from threading import Thread
from yandexmap_parser import YandexMapAccidentParser

app = Flask(__name__)
SETTINGS_FILE = 'settings.json'
bot_thread = None
running = False


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    else:
        default = {
            "lat_start": 55.60,
            "lat_end": 55.90,
            "lon_start": 37.40,
            "lon_end": 37.90,
            "interval": 60,
            "bot_token": ""
        }
        save_settings(default)
        return default


def save_settings(data):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def stop_bot():
    global running
    running = False


def start_bot():
    global bot_thread, running

    if running:
        return

    def run_bot():
        global running
        running = True
        parser = YandexMapAccidentParser(running_flag=lambda: running)
        parser.run()
        running = False

    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        new_settings = {
            "lat_start": float(request.form["lat_start"]),
            "lat_end": float(request.form["lat_end"]),
            "lon_start": float(request.form["lon_start"]),
            "lon_end": float(request.form["lon_end"]),
            "interval": int(request.form["interval"]),
            "bot_token": request.form["bot_token"]
        }
        save_settings(new_settings)

        if running:
            stop_bot()
        start_bot()

        return redirect("/")

    current = load_settings()
    status = "🟢 Работает" if running else "🔴 Остановлен"
    return render_template("index.html", settings=current, status=status, running=running)


@app.route("/start")
def start_manual():
    if not running:
        start_bot()
    return redirect("/")


@app.route("/stop")
def stop_manual():
    stop_bot()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True, port=5000)