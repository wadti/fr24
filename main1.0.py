'''
# Sebastian Gabler, 26/05/2021
# Webscraper for depature times of specified airports
# crawls Flightradar24 and only outputs flights that actually departed
#---------------------------------------------------------------------
# New in V1.1:
# * Fixed bug with daychanges
# * Writes json data directly to docker
'''

# Imports
import pandas as pd
import selenium.webdriver as webdriver
from bs4 import BeautifulSoup
import time
import datetime
from datetime import datetime
from random import randrange
import json
from jsonbender import bend, S
import requests
import os


# Setup
# ------------------------------
# Airports to scrape
depAirports = ["MUC", "FRA", "VIE", "LHR"]
# Address of SEMCON docker
#dockerAddress = 'http://localhost:4000/api/data'
dockerEnv = os.environ["POSTPATH"]
dockerAddress = "http://" + dockerEnv + ":3000/api/data"
# ------------------------------

def get_pageSource(depAirport):
    site = "http://www.flightradar24.com/data/airports/" + depAirport + "/departures"

    chromeOptions = webdriver.ChromeOptions()
    #chromeOptions.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    chromeOptions.add_argument("--no-sandbox")
    chromeOptions.add_argument("--disable-setuid-sandbox")
    #chromeOptions.add_argument("--remote-debugging-port=9222")
    #chromeOptions.add_argument("--disable-dev-shm-using")
    #chromeOptions.add_argument("--disable-extensions")
    #chromeOptions.add_argument("--disable-gpu")
    chromeOptions.add_argument("--headless")  # Don't open window
    chromeOptions.add_argument("disable-infobars")
    #chromeOptions.add_argument(r"user-data-dir=.\cookies\\test")
    driver = webdriver.Chrome("/usr/local/bin/chromedriver", options=chromeOptions) #"/usr/local/bin/chromedriver" ,

    try:
        driver.get(site)
        print("Got site")
    except:
        print("Failed to get site")

    print("# Waiting for page to be loaded...")
    time.sleep(5)
    # Find button to load earlier flights (to get DEP in statusText)
    driver.find_element_by_xpath(
        '/html/body/div[6]/div[2]/section/div/section/div/div[2]/div/aside/div[1]/table/thead/tr[2]/td/button').click()
    print("# Button clicked once...")
    print("# Waiting for page to be loaded...")
    time.sleep(5)
    html = driver.page_source
    driver.quit()

    return html


def get_flightData(html, depAirport):
    soupObj = BeautifulSoup(html, 'html.parser')  # Parser for correct format of html doc
    flightTable = soupObj.find("table", {
        "class": "table table-condensed table-hover data-table m-n-t-15"})  # Find flighttable in HTML
    rows = flightTable.find_all("tr", {"class": "hidden-xs hidden-sm ng-scope"})  # Find all rows in flighttable

    #get date from table
    dateStr = flightTable.find("tr", {"class": "row-date-separator hidden-xs hidden-sm"})  # find date in flighttable

    # get flightinfo rowwise and append to list
    flightData = []
    for row in rows:
        cols = row.find_all('td')
        cols = [x.text.strip() for x in cols]
        flightData.append(cols)

    # convert list to dataframe
    df = pd.DataFrame(flightData, columns=["planedDep", "flightNr", "dest", "operator", "typeReg", "None", "status"])
    df["depCode"] = depAirport  # set depature airport in dataframe (in case of scraping multiple airports)

    # cleaning the data
    # splitting columns
    df[["destName", "destCode"]] = df.dest.str.split("(", expand=True)
    df[["aircraftType", "registration"]] = df.typeReg.str.split("(", expand=True)
    df[["statusText", "statusTime"]] = df.status.str.split(" ", 1, expand=True)

    # dropping unnecassary columns
    df = df.drop(columns=["dest", "typeReg", "None", "status"])

    # Remove hyphens on `operator` and `destCode`
    df["operator"] = df["operator"].str.replace("-", "")
    df["destCode"] = df["destCode"].str.replace("-", "")

    # stripping columns
    # brackets
    df = df.applymap(lambda x: x.replace("(", "") if isinstance(x, str) else x)
    df = df.applymap(lambda x: x.replace(")", "") if isinstance(x, str) else x)
    # spaces
    df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    # est dep.
    df = df.applymap(lambda x: x.replace("dep.  ", "") if isinstance(x, str) else x)

    # clean up aircraft types
    aircraftDict = {"220": "A220", "300": "A300", "310": "A310", '318': "A318", "319": "A319", '320': "A320",
                    "32N": "A320", "A20N": "A320", "321": "A321",
                    "A21N": "A321", "320neo": "A320", '32A': "A320", "321neo": "A320", "32Q": "A321", "330": "A320",
                    "330neo": "A330", "33X": "A330", "A333": "A330", "340": "A340",
                    "350": "A350", "351": "A350", "A35K": "A350", "359": "A350", "A359": "A350", "380": "A380",
                    "388": "A380", "77W": "B777", "77F": "B77F", "73P": "B737", "B38M": "B737", "738": "B737",
                    "74N": "B747", "73H": "B737", "B739": "B737", "B39M": "B737", "777": "B777", "788": "B787",
                    "789": "B787", "B738": "B737", "B763": "B767", "B764": "B767", "B772": "B777",
                    "B773": "B777", "B77W": "B777", "B78X": "B787", "B788": "B787", "B789": "B787", "ER3": "E135",
                    "ER4": "E145", "E70": "E170", "E75": "E175", "E75L": "E175",
                    "E90": "E190", "E95": "E195"}
    df["aircraftType"] = df["aircraftType"].map(aircraftDict).fillna(df["aircraftType"])

    # clean up statusText and drop everything except DEP
    statusTextDict = {'Estimated': "EST",
                      'Scheduled': "STD",
                      'Canceled': "CNL",
                      'Departed': "DEP"}
    df["statusText"] = df["statusText"].map(statusTextDict).fillna(df["statusText"])

    # drop rows where statusText != DEP (only keep departed flights)
    df = df.drop(df[df.statusText != "DEP"].index)

    # Remove special liveries
    df.loc[df["operator"].str.startswith('Etihad'), "operator"] = 'Etihad'
    df.loc[df["operator"].str.startswith('Emirates'), "operator"] = 'Emirates'
    df.loc[df["operator"].str.startswith('Qatar'), "operator"] = 'Qatar'
    df.loc[df["operator"].str.startswith('KLM'), "operator"] = 'KLM'
    df.loc[df["operator"].str.startswith('Austrian Airlines'), "operator"] = 'Austrian Airlines'
    df.loc[df["operator"].str.startswith('United Airlines'), "operator"] = 'United Airlines'
    df.loc[df["operator"].str.startswith('Saudia'), "operator"] = 'Saudia'

    # check for daychange in flightdata
    df["dayChangePlaned"] = df["planedDep"]  # copies column
    df["dayChangeStatus"] = df["statusTime"]  # copies column
    df[["TEMP1", "AM_PM_Planed"]] = df.dayChangePlaned.str.split(" ", expand=True)  # splits column
    df[["TEMP2", "AM_PM_Status"]] = df.dayChangeStatus.str.split(" ", expand=True)  # splits column
    df = df.drop(columns=["dayChangePlaned", "TEMP1"]) #drop what we dont need
    df = df.drop(columns=["dayChangeStatus", "TEMP2"]) #drop what we dont need
    df["dayChangePlaned"] = df["AM_PM_Planed"].shift(1, fill_value=df["AM_PM_Planed"].head(1)) != df["AM_PM_Planed"]
    df["dayChangeStatus"] = df["AM_PM_Status"].shift(1, fill_value=df["AM_PM_Status"].head(1)) != df["AM_PM_Status"]
    df.reset_index(drop=True)
    #Index of daychange_palaned
    indexDaychangePlaned = df.index[df['dayChangePlaned'] == True]
    indexDaychangePlaned = list(indexDaychangePlaned)
    #Index of daychange_status
    indexDaychangeStatus = df.index[df['dayChangeStatus'] == True]
    indexDaychangeStatus = list(indexDaychangeStatus)

    if len(indexDaychangeStatus) == 0:
        print("No daychange found...")
    else:
        for i in range(len(indexDaychangeStatus)):
            if df["planedDep"][indexDaychangeStatus[i]].endswith("AM") and df["statusTime"][indexDaychangeStatus[i]].endswith("PM"):
                df.at[indexDaychangeStatus[i], "dayChangeStatus"] = False
            elif df["planedDep"][indexDaychangeStatus[i]].endswith("AM") and df["statusTime"][indexDaychangeStatus[i]].endswith("PM"):
                df.at[indexDaychangeStatus[i], "dayChangeStatus"] = False

    if len(indexDaychangePlaned) == 0:
        print("No daychange found...")
    else:
        for i in range(len(indexDaychangePlaned)):
            if df["planedDep"][indexDaychangePlaned[i]].startswith("12") and df["planedDep"][indexDaychangePlaned[i]].endswith("PM"):
                df.at[indexDaychangePlaned[i], "dayChangePlaned"] = False

    df["addDay"] = False

    # clean up
    if len(indexDaychangeStatus) == 0:
        print("No daychange found...")
    else:
        for i in range(len(indexDaychangeStatus)):
            if df["planedDep"][indexDaychangeStatus[i]].endswith("PM") and df["statusTime"][indexDaychangeStatus[i]].endswith("AM"):
                df.at[indexDaychangeStatus[i], "addDay"] = True
                df.at[indexDaychangeStatus[i], "dayChangeStatus"] = False

    # clean up
    if len(indexDaychangeStatus) == 0:
        print("No daychange found...")
    else:
        for i in range(len(indexDaychangeStatus)):
            if df["planedDep"][indexDaychangeStatus[i]].endswith("PM") and df["statusTime"][indexDaychangeStatus[i]].endswith("PM"):
                df.at[indexDaychangeStatus[i], "dayChangeStatus"] = False

    # Get new flags
    #Index of daychange_palaned
    indexDaychangePlaned = df.index[df['dayChangePlaned'] == True]
    indexDaychangePlaned = list(indexDaychangePlaned)
    #Index of daychange_status
    indexDaychangeStatus = df.index[df['dayChangeStatus'] == True]
    indexDaychangeStatus = list(indexDaychangeStatus)

    for i in range(len(indexDaychangeStatus)):
        if len(indexDaychangePlaned) != len(indexDaychangeStatus):
            if df["planedDep"][indexDaychangeStatus[-1]].endswith("AM") and df["statusTime"][indexDaychangeStatus[-1]].endswith("AM"):
                df.at[indexDaychangeStatus[-1], "dayChangeStatus"] = False
                indexDaychangeStatus = df.index[df['dayChangeStatus'] == True]
                indexDaychangeStatus = list(indexDaychangeStatus)

    # depPlaned and statusTime to datetime format
    # append string with infos for conversion
    dateTable = str(dateStr.string) #Conversion to sring, otherwise exception
    df["planedDep"] = df["planedDep"] + " " + dateTable + " " + str(datetime.now().year)
    df["statusTime"] = df["statusTime"] + " " + dateTable + " " + str(datetime.now().year)
    # change to datetime
    df["planedDep"] = pd.to_datetime(df["planedDep"], format='%I:%M %p %A, %b %d %Y')
    df["statusTime"] = pd.to_datetime(df["statusTime"], format='%I:%M %p %A, %b %d %Y')

    # increment day in case of daychange
    if len(indexDaychangePlaned) == 0:
        print("No daychange found...")
    else:
        for i in range(len(indexDaychangePlaned)):
            if df.loc[indexDaychangePlaned[i]]["dayChangePlaned"] == True:
                df.loc[indexDaychangePlaned[i]:, ["planedDep"]] = df.loc[indexDaychangePlaned[0]:]["planedDep"] + pd.DateOffset(1)

    if len(indexDaychangeStatus) == 0:
        print("No daychange found...")
    else:
        for i in range(len(indexDaychangeStatus)):
            if df.loc[indexDaychangeStatus[i]]["dayChangeStatus"] == True:
                df.loc[indexDaychangeStatus[i]:, ["statusTime"]] = df.loc[indexDaychangeStatus[0]:]["statusTime"] + pd.DateOffset(1)

    # Add day in case of planed=PM, dep=AM
    df.loc[df['addDay'] == True, "statusTime"] = df.loc[df['addDay'] == True, "statusTime"] + pd.DateOffset(1)

    #Drop columns
    df = df.drop(columns=["AM_PM_Planed", "dayChangePlaned", "AM_PM_Status", "dayChangeStatus", "addDay"])

    # generate key for docker
    df["key"] = df["planedDep"].dt.date.astype(str)
    df["key"] = df["key"].str.replace("-", "")
    df["key"] = df["key"] + "_" + df["flightNr"]

    # calculate delay
    df["delay"] = (df["statusTime"] - df["planedDep"]).astype('timedelta64[m]')

    #format flightdata as json
    flightData = df.to_json(orient="records", date_format="iso")
    parsed = json.loads(flightData)

    #refine data for docker
    dockerMapping = {
        "content": {"planedDep": S("planedDep"),
                    "flightNr": S("flightNr"),
                    "operator": S("operator"),
                    "depCode": S("depCode"),
                    "destName": S("destName"),
                    "destCode": S("destCode"),
                    "aircraftType": S("aircraftType"),
                    "registration": S("registration"),
                    "statusText": S("statusText"),
                    "statusTime": S("statusTime"),
                    "delay": S("delay")},
        "dri": S("key")
    }

    dockerData = []
    for i in range(len(parsed)):
        result = bend(dockerMapping, parsed[i])
        dockerData.append(result)

    return dockerData

def writetodocker(dockerData, dockerAddress):
    headers = {'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
    try:
        requests.post(dockerAddress, json=dockerData, headers=headers)
        print("Request OK")
    except:
        print("Request failed")

def Main(depAirports):
    for i in range(len(depAirports)):
        depAirport = depAirports[i] #use ith airport in list
        print("# Starting with " + depAirport)

        randomTimeout = randrange(60)
        print("# Waiting for " + str(randomTimeout) + " seconds...") #not to raise alarm
        time.sleep(randomTimeout)

        print("# Running selenuim to get page source for " + depAirport + "...")
        html = get_pageSource(depAirport)
        print("#  Pagesource for " + depAirport + " found!")
        print("#  Obtaining flight data...")
        dockerData = get_flightData(html, depAirport)
        writetodocker(dockerData, dockerAddress)
        print("#  FlightData written to docker!")


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    Main(depAirports)