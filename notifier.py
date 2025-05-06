import requests
import json
import os
import time


class TelegramNotifier:
    def __init__(self, bot_token, chats_file='known_chats.json', coord_file='sent_coords.json'):
        self.bot_token = bot_token
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.chats_file = chats_file
        self.coord_file = coord_file
        self.chat_ids = self.load_chat_ids()
        self.sent_coords = self.load_sent_coords()

    def load_chat_ids(self):
        if os.path.exists(self.chats_file):
            with open(self.chats_file, 'r') as f:
                return set(json.load(f))
        return set()

    def save_chat_ids(self):
        with open(self.chats_file, 'w') as f:
            json.dump(list(self.chat_ids), f)

    def poll_new_chats(self):
        try:
            resp = requests.get(f"{self.api_url}/getUpdates", timeout=10)
            updates = resp.json().get("result", [])
            for update in updates:
                chat = update.get("message", {}).get("chat")
                if chat:
                    chat_id = chat["id"]
                    if chat_id not in self.chat_ids:
                        self.chat_ids.add(chat_id)
                        self.save_chat_ids()
        except Exception as e:
            print(f"[Ошибка получения чатов] {e}")

    def load_sent_coords(self):
        if os.path.exists(self.coord_file):
            with open(self.coord_file, 'r') as f:
                return json.load(f)
        return {}

    def save_sent_coords(self):
        with open(self.coord_file, 'w') as f:
            json.dump(self.sent_coords, f, indent=2)

    def cleanup_old_coords(self):
        now = int(time.time())
        self.sent_coords = {
            key: ts for key, ts in self.sent_coords.items()
            if now - ts < 10800
        }
        self.save_sent_coords()

    def coord_key(self, lat, lon):
        return f"{round(lat, 6)}_{round(lon, 6)}"

    def should_send(self, latlon):
        self.cleanup_old_coords()
        key = self.coord_key(*latlon)
        return key not in self.sent_coords

    def mark_sent(self, latlon):
        key = self.coord_key(*latlon)
        self.sent_coords[key] = int(time.time())
        self.save_sent_coords()

    def send_alert(self, lat, lon):
        self.poll_new_chats()
        lat, lon = round(lat, 6), round(lon, 6)
        url = f"https://yandex.ru/maps/213/moscow/probki/?ll={lon}%2C{lat}&z=17"
        text = f"🚨 Обнаружено ДТП:\n{url}"

        for chat_id in self.chat_ids:
            try:
                resp = requests.post(f"{self.api_url}/sendMessage", data={
                    "chat_id": chat_id,
                    "text": text
                })
                if resp.status_code != 200:
                    print(f"[Ошибка отправки в чат {chat_id}] {resp.text}")
            except Exception as e:
                print(f"[Ошибка отправки в чат {chat_id}] {e}")