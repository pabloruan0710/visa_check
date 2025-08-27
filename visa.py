# -*- coding: utf8 -*-

import time
import json
import random
import platform
import configparser
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from random import randrange
import logging
import traceback
load_dotenv()

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

# Função para obter a variável do .env ou fallback para o arquivo .ini
def get_env_or_ini(env_var, section, key, default=None):
    # Primeiro tenta obter do arquivo .env
    value = os.environ.get(env_var)
    if value is not None:
        return value

    # Se não encontrou no .env, tenta pegar do arquivo .ini
    if config.has_option(section, key):
        return config.get(section, key)
    
    # Caso não encontre nem no .env nem no .ini, retorna o valor padrão
    return default

# Configuração das variáveis com fallback
USERNAME = get_env_or_ini("USVISA_USERNAME", "USVISA", "USERNAME")
PASSWORD = get_env_or_ini("USVISA_PASS", "USVISA", "PASSWORD")
SCHEDULE_ID = get_env_or_ini("USVISA_SCHEDULE_ID", "USVISA", "SCHEDULE_ID")
MY_SCHEDULE_DATE = get_env_or_ini("USVISA_MY_SCHEDULE_DATE", "USVISA", "MY_SCHEDULE_DATE")
DAYS_FOR_ORGANIZE = get_env_or_ini("USVISA_DAYS_FOR_ORGANIZE", "USVISA", "DAYS_FOR_ORGANIZE")
CASV_HOUR_DELAY = int(get_env_or_ini("USVISA_CASV_HOUR_DELAY", "USVISA", "CASV_HOUR_DELAY", 0))
COUNTRY_CODE = get_env_or_ini("USVISA_COUNTRY_CODE", "USVISA", "COUNTRY_CODE")
FACILITY_IDS = get_env_or_ini("USVISA_CONSULATE_ID", "USVISA", "FACILITY_ID")
CASV_IDS = get_env_or_ini("USVISA_CASV_ID", "USVISA", "CASV_ID")

SENDGRID_API_KEY = False
PUSH_TOKEN = get_env_or_ini("PUSHOVER_TOKEN", "PUSHOVER", "PUSH_TOKEN")
PUSH_USER = get_env_or_ini("PUSHOVER_USER", "PUSHOVER", "PUSH_USER")
PUSH_DEVICE = get_env_or_ini("PUSHOVER_DEVICE", "PUSHOVER", "PUSH_DEVICE")

LOCAL_USE = eval(get_env_or_ini("LOCAL_USE", "CHROMEDRIVER", "LOCAL_USE", 'False'))
HUB_ADDRESS = "http://localhost:9515/wd/hub"
HEROKU = eval(get_env_or_ini("HEROKU", "CHROMEDRIVER", "HEROKU", 'False'))

ENABLE_RESCHEDULE = config.getboolean('USVISA', 'ENABLE_RESCHEDULE', fallback=eval(get_env_or_ini("ENABLE_RESCHEDULE", "USVISA", "ENABLE_RESCHEDULE", "False")))
REAGENDAR = config.getboolean('USVISA', 'REAGENDAR', fallback=eval(get_env_or_ini("REAGENDAR", "USVISA", "REAGENDAR", "False")))
TELEGRAM_ENABLE = eval(get_env_or_ini("TELEGRAM_ENABLE", "TELEGRAM", "ENABLE", 'True'))
TELEGRAM_BOT_TOKEN = get_env_or_ini("TELEGRAM_BOT_TOKEN", "TELEGRAM", "BOT_TOKEN")
TELEGRAM_CHAT_ID = get_env_or_ini("TELEGRAM_CHAT_ID", "TELEGRAM", "CHAT_ID")
SEND_ERROR_MESSAGE = config.getboolean('NOTIFICACAO', 'SEND_ERROR_MESSAGE', fallback=str(get_env_or_ini("SEND_ERROR_MESSAGE", "NOTIFICACAO", "SEND_ERROR_MESSAGE", "False")).lower() == "true")

REGEX_CONTINUE = "//a[contains(text(),'Continuar')]"
# def MY_CONDITION(month, day): return int(month) == 11 and int(day) >= 5
def MY_CONDITION(month, day): return True # No custom condition wanted for the new scheduled date

STEP_TIME = 0.6  # time between steps (interactions with forms): 0.5 seconds
RETRY_TIME = 60*random.randint(10, 16)  # wait time between retries/checks for available dates: 10 minutes
EXCEPTION_TIME = 60*60  # wait time when an exception occurs: 30 minutes
COOLDOWN_TIME = 60*60  # wait time when temporary banned (empty list): 60 minutes

#DATE_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/days/{FACILITY_ID}.json?appointments[expedite]=false"
#TIME_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/times/{FACILITY_ID}.json?date=%s&appointments[expedite]=false"
#CASV_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/days/{CASV_ID}.json?&consulate_id={FACILITY_ID}&consulate_date=%s&consulate_time=%s&appointments[expedite]=false"
# first %s = date for list time, second %s date consulate, three %s time consulate
#CASV_TIME_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/times/{CASV_ID}.json?date=%s&consulate_id={FACILITY_ID}&consulate_date=%s&consulate_time=%s&appointments[expedite]=false"
APPOINTMENT_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment"
EXIT = False
HEADERS = None
COOKIES = None

def DATE_URL(facilityId):
    return f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/days/{facilityId}.json?appointments[expedite]=false"

def TIME_URL(facilityId):
    return f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/times/{facilityId}.json?date=%s&appointments[expedite]=false"

def CASV_URL(casvId, facilityId):
    return f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/days/{casvId}.json?&consulate_id={facilityId}&consulate_date=%s&consulate_time=%s&appointments[expedite]=false"

def CASV_TIME_URL(casvId, facilityId):
    return f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/times/{casvId}.json?date=%s&consulate_id={facilityId}&consulate_date=%s&consulate_time=%s&appointments[expedite]=false"

def sleep(second):
    time.sleep(second)

def send_notification(msg):
    print(f"\n✅ Sending notification: {msg} token: {PUSH_TOKEN} - {PUSH_USER} - {PUSH_DEVICE}")

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
    # Habilitar a captura de logs de performance
    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})  # Enable performance logs
    if HEROKU:
        chrome_options.binary_location = os.environ.get("GOOGLE_CHROME_BIN")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
    if LOCAL_USE:
        dr = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    else:
        dr = webdriver.Remote(command_executor=HUB_ADDRESS, options=chrome_options)
    
    if HEROKU:
        executable_path=os.environ.get("CHROMEDRIVER_PATH")
        if executable_path is None:
            raise Exception("CHROMEDRIVER_PATH not defined in Env")
        # Passar o caminho específico do ChromeDriver para o Service
        service = Service(executable_path=executable_path)
        dr = webdriver.Chrome(service=service, options=chrome_options)
    dr.execute_cdp_cmd("Network.enable", {})
    return dr

driver = get_driver()
def reloadDriver():
    driver = get_driver()


def login():
    # Bypass reCAPTCHA
    driver.get(f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv")
    time.sleep(STEP_TIME)
    a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
    a.click()
    time.sleep(STEP_TIME)

    print("Login start...")
    href = driver.find_element(By.XPATH, '//*[@id="header"]/nav/div[1]/div[1]/div[2]/div[1]/ul/li[3]/a')
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
    
def do_logout_action():
    global HEADERS
    global COOKIES
    driver.get(f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/users/sign_out")
    time.sleep(random.randint(1, 3))
    HEADERS = None
    COOKIES = None
    driver.close()
    driver.quit()


def get_date(consuladoId):
    sleep(2)
    dates = make_request_with_headers(driver, DATE_URL(consuladoId))
    print(dates)
    print(f"Consulta data para consulado [{consuladoId}]")
    print_dates(dates)
    return dates
    if not is_logged_in():
        console.log('não está logado')
        login()
        return get_date(consuladoId)
    else:
        content = driver.find_element(By.TAG_NAME, 'pre').text
        date = json.loads(content)
        return date

# Função para capturar headers da requisição anterior
def capture_request_headers(driver, target_url_part, timeout=10):
    driver.execute_cdp_cmd('Network.enable', {})  # Ativar a interceptação de rede

    start_time = time.time()
    request_headers = None

    while time.time() - start_time < timeout:
        logs = driver.get_log("performance")  # Obtém os logs de performance

        # Procura pela requisição que contém o target_url_part
        for entry in logs:
            log_msg = json.loads(entry["message"])
            message = log_msg.get("message", {})

            # Verifica se a requisição de rede foi enviada
            if message.get("method") == "Network.requestWillBeSent":
                request_url = message["params"]["request"]["url"]

                if target_url_part in request_url:  # Verifica se é a URL de interesse
                    print(f"Matched Request: {request_url}")
                    request_headers = message["params"]["request"]["headers"]  # Captura os headers
                    break

        if request_headers:
            break
        time.sleep(0.5)  # Espera antes de verificar novamente

    if request_headers:
        return request_headers
    else:
        print("No matching request found within timeout.")
        return None

def get_response_body(driver, target_url_part, timeout=10):
    """
    Captures the response body of a specific request in Selenium using CDP.
    Returns the parsed response as a Python object.

    :param driver: Selenium WebDriver instance
    :param target_url_part: Part of the URL to match (e.g., "/appointment/days/")
    :param timeout: Maximum time (in seconds) to wait for the response
    :return: Parsed response as a Python object, or None if not found
    """
    start_time = time.time()
    matching_request_id = None
    print(f"targetUrl - {target_url_part}")
    while time.time() - start_time < timeout:
        logs = driver.get_log("performance")

        # Step 1: Find the request ID for the target request
        for entry in logs:
            log_msg = json.loads(entry["message"])
            message = log_msg["message"]

            if message["method"] == "Network.requestWillBeSent":
                request_url = message["params"]["request"]["url"]

                if target_url_part in request_url:
                    print(f"Matched Request: {request_url}")
                    matching_request_id = message["params"]["requestId"]
                    break  # Stop once we find the target request

        # Step 2: Fetch the response if requestId was found
        if matching_request_id:
            for entry in logs:
                log_msg = json.loads(entry["message"])
                message = log_msg["message"]

                if message["method"] == "Network.responseReceived":
                    if message["params"]["requestId"] == matching_request_id:
                        # Get response body
                        response = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": matching_request_id})
                        body = response.get("body", None)

                        # Step 3: Parse the response body to a Python object
                        if body:
                            try:
                                # Decode the base64 encoded body (if it's base64 encoded)
                                decoded_body = json.loads(body) if isinstance(body, str) else body
                                return decoded_body  # Parsed Python object (e.g., dictionary)
                            except json.JSONDecodeError:
                                print("Failed to parse response body as JSON.")
                                return None

        time.sleep(0.5)  # Short delay before rechecking logs

    print("No matching response found within timeout.")
    return None


# Função principal para realizar a requisição
def make_request_with_headers(driver, target_url):
    global HEADERS
    if HEADERS is None:
        HEADERS = capture_request_headers(driver, f'/appointment/days')
    global COOKIES
    if COOKIES is None:
        COOKIES = driver.get_cookies()
    cookie_dict = {cookie['name']: cookie['value'] for cookie in COOKIES}
    print(f"Making request {target_url}")
    response = requests.get(target_url, cookies=cookie_dict,  headers=HEADERS)
    print(f"Headers", HEADERS)
    if response.status_code == 200:
        try:
            return response.json() 
        except ValueError:
            print("Erro ao parsear a resposta como JSON")
            return None
    else:
        print(f"Falha na requisição: {response.status_code}")
        print(response)
        return None


def get_time(date, consuladoId):
    sleep(2)
    time_url = TIME_URL(consuladoId) % date
    data = make_request_with_headers(driver, time_url)
    print(f"Times {consuladoId} - {data}")
    if data is None:
        return None
    time = data.get("available_times")[-1]
    print(f"Got time successfully! {date} {time}")
    return time

## CASV
def get_date_casv(date_consulate, time_consulate, consuladoId, casvId):
    sleep(2)
    url = CASV_URL(casvId, consuladoId) % (date_consulate, time_consulate)
    dates = make_request_with_headers(driver, url)
    print(f"Dates cavs {casvId}, dates f{dates}")
    if dates is None:
        return []
    print_dates(dates)
    return dates

    if not is_logged_in():
        login()
        return get_date_casv(date_consulate, time_consulate, consuladoId, casvId)
    else:
        content = driver.find_element(By.TAG_NAME, 'pre').text
        date = json.loads(content)
        print("All dates")
        print_dates(date)
        return date

def get_time_casv(dateListTime, date_consulate, time_consulate, consuladoId, casvId):
    
    def get_time_delay(time):
        consulateTime = datetime.strptime(time_consulate, "%H:%M") + timedelta(hours=CASV_HOUR_DELAY)
        newTime = datetime.strptime(time, "%H:%M")
        print(f"Checando hora do CASV: {newTime} < Consulado: {consulateTime}")
        return newTime < consulateTime

    time_url = CASV_TIME_URL(casvId, consuladoId) % (dateListTime, date_consulate, time_consulate)
    data = make_request_with_headers(driver, time_url)
    print(f"Horarios casv {casvId} - {data}")
    resultTimes = data.get("available_times")
    times = reversed(resultTimes)
    if dateListTime != date_consulate and len(resultTimes) > 0:
        return resultTimes[-1]
        
    for time in times:
        if get_time_delay(time) == True:
            print(f"Got time successfully! {date_consulate} {time}")
            return time


def reschedule(dateConsulate, timeConsulate, dateCasv, timeCasv, consuladoId, casvId = None):
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
            "appointments[consulate_appointment][facility_id]": consuladoId,
            "appointments[consulate_appointment][date]": date,
            "appointments[consulate_appointment][time]": time,
        }

        if casvId is not None and dateCasv and timeCasv:
            data["appointments[asc_appointment][facility_id]"] = casvId
            data["appointments[asc_appointment][date]"] = dateCasv
            data["appointments[asc_appointment][time]"] = timeCasv
        global COOKIES
        if COOKIES is None:
            COOKIES = driver.getCookies()
        cookie_dict = {cookie['name']: cookie['value'] for cookie in COOKIES}
        
        headers = HEADERS

        if casvId is not None and (not dateCasv or not timeCasv):
            msg = f"Data para consulado disponível, porém data não encontrada para CASV! {date} {time}"
            send_notification(msg)
        else:
            print(f"Realizando agendamento")
            print(f"Consulado: {date} - {time}")
            if casvId is not None:
                print(f"CASV: {dateCasv} - {timeCasv}")

            if REAGENDAR == True:
                r = requests.post(APPOINTMENT_URL, cookies=cookie_dict, headers=headers, data=data)
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
                msg = f"Data disponível {date}, hora {time}"
                send_notification(msg)
                print("Reagendamento não realizado, pois REAGENDAR está desabilitado.")
    
            
    else:
        msg = f"{consuladoId} - Nova data disponível! {date} {time}"
        if dateCasv and timeCasv:
             msg = f"{consuladoId} - Nova data disponível! CASV {dateCasv} {timeCasv}, Consulado {date} {time}"
        send_notification(msg)
        #EXIT = True


def is_logged_in():
    content = driver.page_source
    if(content.find(SCHEDULE_ID) >= 0):
        return True
    return False


def print_dates(dates):
    print("Datas disponíveis:")
    if dates is None:
        print("None")
        return
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
            else:
                print(f"Date {date} - lastSeen {last_seen}")


def push_notification(dates):
    msg = "data: "
    for d in dates:
        msg = msg + d.get('date') + '; '
    send_notification(msg)

def consultaDisponibilidade(consuladoId, casvId, retry_count, hasData):
    print("------------------")
    print(datetime.today())
    print(f"Contagem de tentativas: {retry_count}")
    print()

    datesLoop = get_date(consuladoId)
    if datesLoop is None:
        datesLoop = []
    datesLoop = datesLoop[:5]
    
    for dateloop in datesLoop:
        dates = [dateloop]
        print(f"Verificando data {dateloop}")
        if not dates:
            msg = "Lista vazia"
            # EXIT = True
        print_dates(dates)
        date = get_available_date(dates)
        if date is not None:
            print(f"Data disponível - {date}")
            send_notification(f"Nova data disponível para consulado {consuladoId} - {date}")
        if date:
            print(f"Nova data: {date}")
            timeConsulate = get_time(date, consuladoId)
            print(f"Horario consulado - {timeConsulate}")
            if casvId and timeConsulate:
                print()
                print(f"Consultando nova data para CASV [{casvId}] com consulado em: {date} - {timeConsulate}")
                
                casvDates = get_date_casv(date, timeConsulate, consuladoId, casvId)
                if not casvDates:
                    msg = f"Lista CASV [{casvId}] vazia"
                    print(msg)
                    # EXIT = True
                casvDates = list(reversed(casvDates))[:5]
                print(f"Datas casv [{casvId}] invertidas")
                print_dates(casvDates)
                casvDate = get_available_date(casvDates, dateMax=date, isCASV=True)
                print()
                if casvDate:
                    print(f"Nova data CASV [{casvId}]: {casvDate}")
                    timeCasv = get_time_casv(casvDate, date, timeConsulate, consuladoId, casvId)
                else:
                    print(f"Data não disponível para CASV {casvId}")
                
                if casvDate and timeCasv:
                    reschedule(date, timeConsulate, casvDate, timeCasv, consuladoId, casvId)
                    break
                else:
                    reschedule(date, timeConsulate, None, None, consuladoId, casvId)
                    break
            else:
                reschedule(date, timeConsulate, None, None, consuladoId, casvId)
                break

    if(EXIT):
        print("------------------exit")
        raise ValueError('------------------exit')

    if not datesLoop and not hasData:
        hasData = False
    else:
        hasData = True
    print("##################\n")

if __name__ == "__main__":
    retry_count = 0
    while 1:
        if retry_count > 6:
            break
        try:
            reloadDriver()
            login()
            driver.get(APPOINTMENT_URL)
            _consulados = FACILITY_IDS.split(",")
            _casvs = []
            if CASV_IDS is not None:
                _casvs = CASV_IDS.split(",")

            indexConsulado = 0
            hasData = False
            for consulado in _consulados:
                last_seen = None
                _idCasv = None
                if indexConsulado < len(_casvs):
                    _idCasv = _casvs[indexConsulado]
                print(f"Consultando disponibilidade para consulado {consulado} e CASV {_idCasv}")
                consultaDisponibilidade(consulado, _idCasv, retry_count, hasData)
                indexConsulado += 1

            if not hasData:
                msg = "Lista vazia"
                print(f"{msg}")
                #EXIT = True
                print(f"Aguardando próximo loop {str(COOLDOWN_TIME/60)} minutos")
                do_logout_action()
                time.sleep(COOLDOWN_TIME)
            else:
                RETRY_TIME = 60*random.randint(9, 16) 
                minutos = RETRY_TIME/60
                print(f"Aguardando {minutos} min...")
                do_logout_action()
                time.sleep(RETRY_TIME)

        except Exception as er:
            if SEND_ERROR_MESSAGE:
                send_notification("Erro no script: " + str(er))
            traceback.print_exc()
            do_logout_action()
            retry_count += 1
            time.sleep(EXCEPTION_TIME)

    if(not EXIT):
        if SEND_ERROR_MESSAGE:
            send_notification("HELP! Crashed.")
