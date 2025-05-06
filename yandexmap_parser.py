import os
import time
import cv2
import math
import json
import numpy as np
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from notifier import TelegramNotifier


class YandexMapAccidentParser:
    def __init__(self, running_flag=None):
        self.is_running = running_flag or (lambda: True)

        with open("settings.json", "r") as f:
            settings = json.load(f)

        self.interval = settings["interval"]
        self.bot_token = settings["bot_token"]
        self.lat_start = settings["lat_start"] 
        self.lat_end = settings["lat_end"] 
        self.lon_start = settings["lon_start"] 
        self.lon_end = settings["lon_end"] 
        lat_step = 0.085
        lon_step = 0.25

        lats = np.arange(self.lat_start, self.lat_end, lat_step)
        lons = np.arange(self.lon_start, self.lon_end, lon_step)
        self.tile_coords = [(round(lat, 5), round(lon, 5)) for lat in lats for lon in lons]
        self.notifier = TelegramNotifier(bot_token=self.bot_token)

        self.screenshot_dir = "screenshots"
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def initialize_browser(self):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        service = Service("chromedriver-win64/chromedriver.exe")
        return webdriver.Chrome(service=service, options=options)
    
    def move_map(self, driver, lat, lon):
        try:
            driver.execute_script(f"yandex_map.setCenter([{lon}, {lat}], 13);")
            time.sleep(0.5)
        except Exception as e:
            print(f"[Ошибка JS-перемещения] {e}")

    def capture_screenshot(self, driver, index):
        temp_path = os.path.join(self.screenshot_dir, f"tile_{index}.png")
        crop_path = os.path.join(self.screenshot_dir, f"tile_crop_{index}.png")

        driver.get_screenshot_as_file(temp_path)

        img = Image.open(temp_path)
        cropped_img = img.crop((384, 0, 1898, 930))
        cropped_img.save(crop_path)
        img.close()
        os.remove(temp_path)
        return crop_path

    def detect_accident(self, image_path, tile_center, index):
        lat_c, lon_c = tile_center
        image = cv2.imread(image_path)
        template = cv2.imread("scr_temp.png")
        h, w = template.shape[:2]
        res = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
        threshold = 0.8

        while True:
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val < threshold:
                break

            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2

            lat, lon = self.pixel_to_geo(center_x, center_y, lat_c, lon_c)

            if self.notifier.should_send((lat, lon)):
                self.notifier.send_alert(lat, lon)
                self.notifier.mark_sent((lat, lon))

            res[max_loc[1]-h//2:max_loc[1]+h//2+1, max_loc[0]-w//2:max_loc[0]+w//2+1] = 0

        os.remove(image_path)

    def lat_per_pixel(self, lat_center_deg, zoom):
        tile_size = 256
        scale = 2 ** zoom
        lat_center_rad = math.radians(lat_center_deg)

        merc_y = (0.5 - math.log(math.tan(math.pi / 4 + lat_center_rad / 2)) / (2 * math.pi)) * tile_size * scale
        delta_y = 1

        y_top = merc_y - delta_y
        n = math.pi - 2 * math.pi * y_top / (tile_size * scale)
        lat_top = math.degrees(math.atan(math.sinh(n)))

        return lat_top - lat_center_deg

    def pixel_to_geo(self, x, y, lat_center, lon_center, width=1514, height=930, zoom=13):
        lon_center += (x - width / 2) * (360 / pow(2, zoom + 8)) - 0.003193
        lat_center += (height / 2 - y) * self.lat_per_pixel(lat_center, zoom)

        return round(lat_center, 6), round(lon_center, 6)

    def run(self):
        driver = self.initialize_browser()
        try:
            print("Загрузка карты...")
            driver.get(f"https://yandex.ru/maps/213/moscow/?l=trf%2Ctrfe&ll={self.lon_start}%2C{self.lat_start}&z=13")
            time.sleep(3)
            print("Карта загружена. Производится поиск...")

            while self.is_running():
                for i, (lat, lon) in enumerate(self.tile_coords):
                    self.move_map(driver, lat, lon)
                    img_path = self.capture_screenshot(driver, i)
                    if img_path:
                        self.detect_accident(img_path, (lat, lon), i)
                    else:
                        print(f"[Пропуск] Не удалось получить скриншот для тайла {i}")
                time.sleep(self.interval)
        finally:
            driver.quit()