import argparse
import copy
import json
import os.path
import socket

import numpy as np
import pandas as pd

from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
import time

# PARSE ARGUMENTS
parser = argparse.ArgumentParser()
parser.add_argument('--quic', action='store_true')
parser.add_argument('--tcp', action='store_true')
parser.add_argument('destServer', type=str,
                    help='destination server (and optional port) without https, e.g., myserver.com:443')
parser.add_argument('iterations', type=int)
args = parser.parse_args()

assert (args.quic and not args.tcp) or (args.tcp and not args.quic)
protocol = "quic" if args.quic else "tcp"
assert args.iterations > 0

# CHROME OPTIONS
options = webdriver.ChromeOptions()

# enable performance and network logging
# https://stackoverflow.com/questions/76792076/setting-logging-prefs-for-chrome-using-selenium-4-10
# https://www.selenium.dev/documentation/webdriver/troubleshooting/upgrade_to_selenium_4/
options.set_capability('goog:loggingPrefs', {'performance': "ALL"})
options.add_argument("--headless")
options.add_argument("--disable-gpu")

if protocol == "tcp":
    options.add_argument("--disable-quic")
else:
    options.add_argument("--enable-quic")
    options.add_argument(f"--origin-to-force-quic-on={args.destServer}")

# CREATE WEBDRIVER
driver = webdriver.Chrome(service=webdriver.chrome.service.Service(ChromeDriverManager().install()), options=options)

# delete cookies
# https://stackoverflow.com/questions/50456783/python-selenium-clear-the-cache-and-cookies-in-my-chrome-webdriver
driver.delete_all_cookies()
# disable cache
# https://stackoverflow.com/questions/66956625/disable-cache-on-network-tab-using-python-seleniumautomation
# https://chromedevtools.github.io/devtools-protocol/tot/Network/#method-setCacheDisabled
driver.execute_cdp_cmd('Network.setCacheDisabled', {'cacheDisabled': True})

# do a warm-up, ignore output (not sure if this makes sense...)
driver.get(f"https://{args.destServer}/vosweb/500k.html")

df = pd.DataFrame()
for iteration in range(args.iterations):
    for size in range(0, 10001, 500): #["0k", "500k", "1000k", "1500k", "2000k", ..., "10000k"]
        print(f"Running iteration {iteration}/{args.iterations} with size {size}")
        driver.get(f"https://{args.destServer}/vosweb/{size}k.html")

        performanceTiming = driver.execute_script("return performance.getEntries()")
        #print(json.dumps(performanceTiming, indent=4))
        #TODO safe as json

        duration = np.nan
        fcp = np.nan
        for entry in performanceTiming:
            if entry['entryType'] == "navigation":
                assert entry['name'] == f"https://{args.destServer}/vosweb/{size}k.html"

                if protocol == "tcp":
                    assert entry['nextHopProtocol'] == 'h2'
                else:
                    assert entry['nextHopProtocol'] == 'h3'
                #print("navigation")
                #print(entry)
                duration = entry['duration']
            if entry['entryType'] == "paint" and entry['name'] == "first-contentful-paint":
                #print("first-contentful-paint")
                #print(entry)
                fcp = entry['startTime']

        df_temp = pd.DataFrame({"Operator": socket.gethostname(),
                                "Protocol": protocol,
                                "Size": size,
                                "Iteration": iteration,
                                "Duration": duration,
                                "FCP": fcp
                                }, index=[0])
        df = pd.concat([df, df_temp]) #concat is very slow :-/
# CLOSE DRIVER
driver.close()

print(df)
df.to_csv(f"result_{socket.gethostname()}_{protocol}.csv")

