import os
import cv2
import time
import numpy as np
import pandas as pd
from PIL import Image
from datetime import datetime
import sqlalchemy
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options


class YandexMapAccidentParser:
    def __init__(self):
        self.info_dict = {'xy_coord': [], 'date': [], 'timestamp': [], 'coord_stamp': []}
        self.session_dict = {'xy_coord': [], 'date': [], 'timestamp': [], 'coord_stamp': []}
        self.region_dict = {
            'Центр': (255, 255, 255), 'Юго-Запад': (0, 38, 255), 'Фили': (182, 255, 0),
            'Строгино': (255, 106, 0), 'Тушино': (178, 0, 255), 'Ховрино': (0, 127, 127),
            'Дмитровка': (38, 127, 0), 'Останкино': (128, 128, 128), 'Медведково': (0, 255, 255),
            'Лефортово': (127, 0, 55), 'Измайлово': (127, 51, 0), 'Перово': (255, 216, 0),
            'Вешняки': (178, 255, 193), 'Кузьминки': (124, 94, 124), 'Люблино': (0, 148, 255),
            'Зябликово': (127, 0, 0), 'Каширка': (56, 54, 63), 'Сукино Болото': (0, 19, 127)
        }
        self.engine = sqlalchemy.create_engine('mysql+mysqlconnector://root:@localhost:3306/accidents')
        self.img_color_dist = Image.open("region_dist_color.png")

        self.screenshot_dir = "screenshots"
        os.makedirs(self.screenshot_dir, exist_ok=True)

        lats = np.linspace(55.60, 55.90, 5)
        lons = np.linspace(37.40, 37.90, 5)
        self.tile_coords = [(round(lat, 5), round(lon, 5)) for lat in lats for lon in lons]

    def get_region(self, xy_coord):
        color = self.img_color_dist.getpixel((xy_coord[0], xy_coord[1]))[:3]
        return next((region for region, rgb in self.region_dict.items() if rgb == color), 'За МКАД')

    def send_to_db(self, df):
        for col in df.columns:
            df[col] = df[col].apply(lambda x: str(x) if isinstance(x, tuple) else x)
        with self.engine.connect() as con:
            df.to_sql('accidents', con, if_exists='append', index=False)

    def initialize_browser(self):
        chromedriver = "chromedriver-win64/chromedriver.exe"
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        service = Service(executable_path=chromedriver)
        return webdriver.Chrome(service=service, options=chrome_options)

    def capture_and_crop_screenshot(self, driver, lat, lon, tile_index):
        zoom = 12
        url = f"https://yandex.ru/maps/213/moscow/?l=trf%2Ctrfe&ll={lon}%2C{lat}&z={zoom}"
        driver.get(url)
        time.sleep(2)

        screenshot_path = os.path.join(self.screenshot_dir, f"screenshot_tile_{tile_index}.png")
        driver.get_screenshot_as_file(screenshot_path)

        img = Image.open(screenshot_path)
        cropped_path = os.path.join(self.screenshot_dir, f"screenshot_crop_{tile_index}.png")
        cropped_img = img.crop((450, 50, 1200, 923))
        cropped_img.save(cropped_path)
        img.close()

    def match_template_and_parse(self, tile_index):
        image = cv2.imread(os.path.join(self.screenshot_dir, f"screenshot_crop_{tile_index}.png"))
        template = cv2.imread("scr_temp.png")
        h, w = template.shape[:2]
        method = cv2.TM_CCOEFF_NORMED
        res = cv2.matchTemplate(image, template, method)
        max_val, x_c, y_c = 1, -10000, -10000
        threshold = 0.8

        while max_val > threshold:
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            new_xc, new_yc = (2 * max_loc[0] + w) / 2, (2 * max_loc[1] + h) / 2
            if (x_c, y_c) == (new_xc, new_yc):
                break
            res[max_loc[1]-h//2:max_loc[1]+h//2+1, max_loc[0]-w//2:max_loc[0]+w//2+1] = 0
            image = cv2.rectangle(image, max_loc, (max_loc[0] + w + 1, max_loc[1] + h + 1), (255, 0, 0))
            x_c, y_c = new_xc, new_yc
            self.update_info((x_c, y_c))

        output_path = os.path.join(self.screenshot_dir, f"output_{tile_index}.png")
        cv2.imwrite(output_path, image)

    def update_info(self, coord):
        x_c, y_c = coord
        timestamp = int(datetime.now().timestamp())
        if coord not in self.info_dict['xy_coord']:
            for d in (self.info_dict, self.session_dict):
                d['xy_coord'].append(coord)
                d['date'].append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                d['timestamp'].append(timestamp)
                d['coord_stamp'].append((x_c, y_c, timestamp))
        elif timestamp - next(z for x, y, z in self.info_dict['coord_stamp'] if x == x_c and y == y_c) > 5000:
            for d in (self.info_dict, self.session_dict):
                d['xy_coord'].append(coord)
                d['date'].append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                d['timestamp'].append(timestamp)
                d['coord_stamp'].append((x_c, y_c, timestamp))

    def process_session_data(self):
        if self.session_dict['xy_coord']:
            df = pd.DataFrame(self.session_dict)
            df['region'] = df.apply(lambda x: self.get_region(x['xy_coord']), axis=1)
            self.send_to_db(df)
            self.session_dict = {'xy_coord': [], 'date': [], 'timestamp': [], 'coord_stamp': []}

    def run(self):
        driver = self.initialize_browser()

        for i, (lat, lon) in enumerate(self.tile_coords):
            self.capture_and_crop_screenshot(driver, lat, lon, i)
            self.match_template_and_parse(i)
            self.process_session_data()

        driver.quit()
        self.img_color_dist.close()


if __name__ == "__main__":
    parser = YandexMapAccidentParser()
    parser.run()