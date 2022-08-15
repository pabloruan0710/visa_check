# -*- coding: utf8 -*-

import time
import json
import random
import platform
import configparser
import os
from datetime import datetime, timedelta
from random import randrange
import logging

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

config = configparser.ConfigParser()
config.read('config.ini')

USERNAME = os.environ.get("USVISA_USERNAME") or config['USVISA']['USERNAME']
PASSWORD = os.environ.get("USVISA_PASS") or config['USVISA']['PASSWORD']
SCHEDULE_ID = os.environ.get("USVISA_SCHEDULE_ID") or config['USVISA']['SCHEDULE_ID']
MY_SCHEDULE_DATE = os.environ.get("USVISA_MY_SCHEDULE_DATE") or config['USVISA']['MY_SCHEDULE_DATE']
DAYS_FOR_ORGANIZE = os.environ.get("USVISA_DAYS_FOR_ORGANIZE") or config['USVISA']['DAYS_FOR_ORGANIZE']
CASV_HOUR_DELAY = os.environ.get("USVISA_CASV_HOUR_DELAY") or int(config['USVISA']['CASV_HOUR_DELAY'] or 0) #quantidade em horas para chegar ao casv
COUNTRY_CODE = os.environ.get("USVISA_COUNTRY_CODE") or config['USVISA']['COUNTRY_CODE']
FACILITY_ID = os.environ.get("USVISA_CONSULATE_ID") or config['USVISA']['FACILITY_ID']
CASV_ID = os.environ.get("USVISA_CASV_ID") or config['USVISA']['CASV_ID']

SENDGRID_API_KEY = False
PUSH_TOKEN = os.environ.get("PUSHOVER_TOKEN") or config['PUSHOVER']['PUSH_TOKEN']
PUSH_USER = os.environ.get("PUSHOVER_USER") or config['PUSHOVER']['PUSH_USER']
PUSH_DEVICE = os.environ.get("PUSHOVER_DEVICE") or config['PUSHOVER']['PUSH_DEVICE']

LOCAL_USE = eval(os.environ.get("LOCAL_USE") or 'False') or config['CHROMEDRIVER'].getboolean('LOCAL_USE')
HUB_ADDRESS = "http://localhost:9515/wd/hub"
HEROKU = eval(os.environ.get("HEROKU") or 'False') or config['CHROMEDRIVER'].getboolean('HEROKU')

REGEX_CONTINUE = "//a[contains(text(),'Continuar')]"

ENABLE_RESCHEDULE = eval(os.environ.get("ENABLE_RESCHEDULE") or 'False') or True
TELEGRAM_ENABLE = eval(os.environ.get("TELEGRAM_ENABLE") or 'True') or config['TELEGRAM'].getboolean('ENABLE')
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or config['TELEGRAM']['BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or config['TELEGRAM']['CHAT_ID']

# def MY_CONDITION(month, day): return int(month) == 11 and int(day) >= 5
def MY_CONDITION(month, day): return True # No custom condition wanted for the new scheduled date

STEP_TIME = 0.5  # time between steps (interactions with forms): 0.5 seconds
RETRY_TIME = 60*random.randint(10, 16)  # wait time between retries/checks for available dates: 10 minutes
EXCEPTION_TIME = 60*30  # wait time when an exception occurs: 30 minutes
COOLDOWN_TIME = 60*60  # wait time when temporary banned (empty list): 60 minutes

DATE_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/days/{FACILITY_ID}.json?appointments[expedite]=false"
TIME_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/times/{FACILITY_ID}.json?date=%s&appointments[expedite]=false"
CASV_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/days/{CASV_ID}.json?&consulate_id={FACILITY_ID}&consulate_date=%s&consulate_time=%s&appointments[expedite]=false"
# first %s = date for list time, second %s date consulate, three %s time consulate
CASV_TIME_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/times/{CASV_ID}.json?date=%s&consulate_id={FACILITY_ID}&consulate_date=%s&consulate_time=%s&appointments[expedite]=false"
APPOINTMENT_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment"
EXIT = False


def send_notification(msg):
    print(f"Sending notification: {msg} token: {PUSH_TOKEN} - {PUSH_USER} - {PUSH_DEVICE}")

    if SENDGRID_API_KEY:
        message = Mail(
            from_email=USERNAME,
            to_emails=USERNAME,
            subject=msg,
            html_content=msg)
        try:
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)
            print(response.status_code)
            print(response.body)
            print(response.headers)
        except Exception as e:
            print(e.message)

    if PUSH_TOKEN:
        url = "https://api.pushover.net/1/messages.json"
        data = {
            "token": PUSH_TOKEN,
            "user": PUSH_USER,
            "device": PUSH_DEVICE,
            "message": msg
        }
        try:
            requests.post(url, data)
        except Exception as e:
            print(e.message)

    if TELEGRAM_ENABLE:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage?chat_id={TELEGRAM_CHAT_ID}&text={msg}"
        requests.get(url)

def get_driver():
    chrome_options = webdriver.ChromeOptions()
    if HEROKU:
        chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
    if LOCAL_USE:
        dr = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    else:
        dr = webdriver.Remote(command_executor=HUB_ADDRESS, options=chrome_options)
    
    if HEROKU:
        #executable_path=os.environ.get("CHROMEDRIVER_PATH"), 
        dr = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return dr

driver = get_driver()


def login():
    # Bypass reCAPTCHA
    driver.get(f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv")
    time.sleep(STEP_TIME)
    a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
    a.click()
    time.sleep(STEP_TIME)

    print("Login start...")
    href = driver.find_element(By.XPATH, '//*[@id="header"]/nav/div[2]/div[1]/ul/li[3]/a')
    href.click()
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "commit")))

    print("\tclick bounce")
    a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
    a.click()
    time.sleep(STEP_TIME)

    do_login_action()


def do_login_action():
    print("\tinput email")
    user = driver.find_element(By.ID, 'user_email')
    user.send_keys(USERNAME)
    time.sleep(random.randint(1, 3))

    print("\tinput pwd")
    pw = driver.find_element(By.ID, 'user_password')
    pw.send_keys(PASSWORD)
    time.sleep(random.randint(1, 3))

    print("\tclick privacy")
    box = driver.find_element(By.CLASS_NAME, 'icheckbox')
    box .click()
    time.sleep(random.randint(1, 3))

    print("\tcommit")
    btn = driver.find_element(By.NAME, 'commit')
    btn.click()
    time.sleep(random.randint(1, 3))

    Wait(driver, 60).until(
        EC.presence_of_element_located((By.XPATH, REGEX_CONTINUE)))
    print("\tlogin successful!")


def get_date():
    driver.get(DATE_URL)
    if not is_logged_in():
        login()
        return get_date()
    else:
        content = driver.find_element(By.TAG_NAME, 'pre').text
        date = json.loads(content)
        return date


def get_time(date):
    time_url = TIME_URL % date
    driver.get(time_url)
    content = driver.find_element(By.TAG_NAME, 'pre').text
    data = json.loads(content)
    time = data.get("available_times")[-1]
    print(f"Got time successfully! {date} {time}")
    return time

## CASV
def get_date_casv(date_consulate, time_consulate):
    url = CASV_URL % (date_consulate, time_consulate)
    driver.get(url)
    if not is_logged_in():
        login()
        return get_date_casv()
    else:
        content = driver.find_element(By.TAG_NAME, 'pre').text
        date = json.loads(content)
        return date

def get_time_casv(dateListTime, date_consulate, time_consulate):
    
    def get_time_delay(time):
        consulateTime = datetime.strptime(time_consulate, "%H:%M") + timedelta(hours=CASV_HOUR_DELAY)
        newTime = datetime.strptime(time, "%H:%M")
        print(f"Checando hora do CASV: {newTime} < Consulado: {consulateTime}")
        return newTime < consulateTime

    time_url = CASV_TIME_URL % (dateListTime, date_consulate, time_consulate)
    driver.get(time_url)
    content = driver.find_element(By.TAG_NAME, 'pre').text
    data = json.loads(content)
    resultTimes = data.get("available_times")
    times = reversed(resultTimes)
    if dateListTime != date_consulate and len(resultTimes) > 0:
        return resultTimes[-1]
        
    for time in times:
        if get_time_delay(time) == True:
            print(f"Got time successfully! {date} {time}")
            return time


def reschedule(dateConsulate, timeConsulate, dateCasv, timeCasv):
    global EXIT
    date = dateConsulate
    time = timeConsulate
    dateCasv = dateCasv
    timeCasv = timeCasv
    driver.get(APPOINTMENT_URL)

    if ENABLE_RESCHEDULE:
        print(f"Starting Reschedule ({date})")
        data = {
            "utf8": driver.find_element(by=By.NAME, value='utf8').get_attribute('value'),
            "authenticity_token": driver.find_element(by=By.NAME, value='authenticity_token').get_attribute('value'),
            "confirmed_limit_message": driver.find_element(by=By.NAME, value='confirmed_limit_message').get_attribute('value'),
            "use_consulate_appointment_capacity": driver.find_element(by=By.NAME, value='use_consulate_appointment_capacity').get_attribute('value'),
            "appointments[consulate_appointment][facility_id]": FACILITY_ID,
            "appointments[consulate_appointment][date]": date,
            "appointments[consulate_appointment][time]": time,
        }

        if CASV_ID and dateCasv and timeCasv:
            data["appointments[asc_appointment][facility_id]"] = CASV_ID
            data["appointments[asc_appointment][date]"] = dateCasv
            data["appointments[asc_appointment][time]"] = timeCasv

        headers = {
            "User-Agent": driver.execute_script("return navigator.userAgent;"),
            "Referer": APPOINTMENT_URL,
            "Cookie": "_yatri_session=" + driver.get_cookie("_yatri_session")["value"]
        }

        if CASV_ID and (not dateCasv or not timeCasv):
            msg = f"Data para consulado disponível, porém data não encontrada para CASV! {date} {time}"
            send_notification(msg)
        else:
            print(f"Realizando agendamento")
            print(f"Consulado: {date} - {time}")
            if CASV_ID:
                print(f"CASV: {dateCasv} - {timeCasv}")

            r = requests.post(APPOINTMENT_URL, headers=headers, data=data)
            print("Retorno reagendamento!")
            print(r)
    
            if(r.text.find('Você realizou o seu agendamento com sucesso') != -1):
                msg = f"Reagendamento realizado! {date} {time}"
                send_notification(msg)
                EXIT = True
            else:
                msg = f"Falha ao reagendar. {date} {time}"
                send_notification(msg)
    else:
        msg = f"{FACILITY_ID} - Nova data disponível! {date} {time}"
        send_notification(msg)
        #EXIT = True


def is_logged_in():
    content = driver.page_source
    if(content.find("error") != -1):
        return False
    return True


def print_dates(dates):
    print("Datas disponíveis:")
    for d in dates:
        print("%s \t business_day: %s" % (d.get('date'), d.get('business_day')))
    print()


last_seen = None


def get_available_date(dates, dateMax=MY_SCHEDULE_DATE, isCASV=False):
    global last_seen

    def is_earlier(date):
        my_date = datetime.strptime(dateMax, "%Y-%m-%d")
        new_date = datetime.strptime(date, "%Y-%m-%d")
        minimum_date = None
        if DAYS_FOR_ORGANIZE:
            minimum_date_d = (datetime.today() + timedelta(days=int(DAYS_FOR_ORGANIZE))).strftime("%Y-%m-%d")
            minimum_date = datetime.strptime(minimum_date_d, "%Y-%m-%d")
        if isCASV:
            if minimum_date:
                result = my_date >= new_date and new_date >= minimum_date
                print(f'Is CASV {my_date} >= {new_date} and {new_date} >= {minimum_date}:\t{result}')
            else:
                result = my_date > new_date
                print(f'Is CASV {my_date} >= {new_date}:\t{result}')
            return result
        else:
            if minimum_date:
                result = my_date > new_date and new_date >= minimum_date
                print(f'Is {my_date} > {new_date} and {new_date} >= {minimum_date}:\t{result}')
            else:
                result = my_date > new_date
                print(f'Is {my_date} >= {new_date}:\t{result}')
            return result

    print("Verificando uma data anterior:")
    for d in dates:
        date = d.get('date')
        if isCASV and is_earlier(date):
            return date
        else:
            if is_earlier(date) and date != last_seen:
                _, month, day = date.split('-')
                if(MY_CONDITION(month, day)):
                    last_seen = date
                    return date


def push_notification(dates):
    msg = "data: "
    for d in dates:
        msg = msg + d.get('date') + '; '
    send_notification(msg)

if __name__ == "__main__":
    login()
    retry_count = 0
    while 1:
        if retry_count > 6:
            break
        try:
            print("------------------")
            print(datetime.today())
            print(f"Contagem de tentativas: {retry_count}")
            print()

            dates = get_date()[:5]
            if not dates:
                msg = "Lista vazia"
               # EXIT = True
            print_dates(dates)
            date = get_available_date(dates)
            print()
            if date:
                print(f"Nova data: {date}")
                timeConsulate = get_time(date)
                if CASV_ID and timeConsulate:
                    print()
                    print(f"Consultando nova data para CASV com consulado em: {date} - {timeConsulate}")
                    casvDates = get_date_casv(date, timeConsulate)[:5]
                    if not casvDates:
                        msg = "Lista CASV vazia"
                        # EXIT = True
                    print_dates(casvDates)
                    casvDate = get_available_date(casvDates, dateMax=date, isCASV=True)
                    print()
                    if casvDate:
                        print(f"Nova data CASV: {casvDate}")
                        timeCasv = get_time_casv(casvDate, date, timeConsulate)
                    else:
                        print(f"Data não disponível para CASV")
                    
                    if casvDate and timeCasv:
                        reschedule(date, timeConsulate, casvDate, timeCasv)
                    else:
                        reschedule(date, timeConsulate, None, None)
                else:
                    reschedule(date, timeConsulate, None, None)

            if(EXIT):
                print("------------------exit")
                break

            if not dates:
                msg = "Lista vazia"
                print(f"{msg}")
                #EXIT = True
                time.sleep(COOLDOWN_TIME)
            else:
                RETRY_TIME = 60*random.randint(9, 16) 
                minutos = RETRY_TIME/60
                print(f"Aguardando {minutos} min...")
                time.sleep(RETRY_TIME)

        except:
            retry_count += 1
            time.sleep(EXCEPTION_TIME)

    if(not EXIT):
        send_notification("HELP! Crashed.")
