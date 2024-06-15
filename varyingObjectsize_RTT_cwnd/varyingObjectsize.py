import argparse
import struct
import subprocess
import re
import time
import glob
from enum import Enum
import json
import numpy as np
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns
import os

# Measure, eval, and plot RTTs (min_rtt, latest_rtt) and congestion_window, bytes_in_flight
#
# Prerequisites and command line arguments:
# 1) Run picoquic or quiche transfers with varying object sizes
#    a) Start picoquic or quiche server on this machine
#       - picoquic must be installed in directory 'picoquic'
#       - quiche must be installed in directory 'quiche/target/release' and objects must be available in directory 'www'
#       - qlog files are only logged on this machine (QUIC server)
#    b) Connects via ssh to different PCs starting picoquic or quiche clients
#       - picoquic must be installed in {remote}:~/picoquic
#       - quiche must be installed in {remote}:~/quiche/target/release
#       - remote ssh login must be possible without password 
#       - no logging in remote PCs (QUIC client)
# 2) Run through all qlog files, extract RTTs and cwnd/bytes_in_flight, write to csv file
# 3) Plot csv file

class Implementation(Enum):
    PICOQUIC = 1
    QUICHE =2

operators = {   "NetEm": {"sshRemoteLogin": "user@netem",    "destIp": "10.37.1.1"}
             #  "Skydsl": {"sshRemoteLogin": "user@skydsl",   "destIp": "131.188.x.y"},
             # "Konnect": {"sshRemoteLogin": "user@konnect",  "destIp": "131.188.x.y"},
             #"Starlink": {"sshRemoteLogin": "user@starlink", "destIp": "131.188.x.y"}
            }

objsizeList = [int(x) for x in [10e3, 30e3, 100e3, 300e3, 1e6, 3e6, 10e6, 30e6, 100e6, 300e6]]


def runPicoquicClient(sshRemoteLogin, ccAlgorithm, destIp, destPort, objsize):
    # -L -l picoquic.textlog #save qlog and textlog output
    # -D                     #no disk: do not save received files on disk
    cmd = f"ssh {sshRemoteLogin} picoquic/picoquicdemo -n xyz -G {ccAlgorithm} {destIp} {destPort} /{objsize}"
    print(cmd)
    subprocess.run(cmd.split())
    time.sleep(2)

def runQuicheClient(sshRemoteLogin, ccAlgorithm, destIp, destPort, objsize):
    cmd = f"ssh {sshRemoteLogin} quiche/target/release/quiche-client --no-verify --cc-algorithm {ccAlgorithm} https://{destIp}:{destPort}/{objsize} > /dev/null"
    print(cmd)
    subprocess.run(cmd.split())
    time.sleep(2)

def waitForQlogFile(path2qlogDir):
    while not glob.glob(f'{path2qlogDir}/*.qlog'):
        print("server *.qlog file not found, waiting...")
        time.sleep(1)

def runImplementation(implementation: Implementation, iterations: int):
    results_dir = "results" #f"results_{datetime.today().strftime('%Y%m%d_%H%M')}"
    temp_qlog_dir = "temp_qlog"
    subprocess.run(f"mkdir -p results", shell=True)
    subprocess.run(f"rm -rf {temp_qlog_dir} && mkdir {temp_qlog_dir}", shell=True)

    for iteration in range(0,iterations):
        for ccAlgorithm in ["cubic", "bbr"]:
            if implementation == Implementation.PICOQUIC:
                print("Starting picoquic server...")
                cmd = f"./picoquic/picoquicdemo -c picoquic/certs/cert.pem -k picoquic/certs/key.pem -p 4431 -q {temp_qlog_dir} -G {ccAlgorithm}"
                print(cmd)
                subprocess.Popen(cmd, shell=True)
                time.sleep(1)

            if implementation == Implementation.QUICHE:
                print("Starting quiche server...")
                cmd = (f"QLOGDIR={temp_qlog_dir} ./quiche/target/release/quiche-server "
                       f"--cert quiche/apps/src/bin/cert.crt "
                       f"--key quiche/apps/src/bin/cert.key "
                       f"--root www --listen 0.0.0.0:4432 "
                       f"--cc-algorithm {ccAlgorithm}")
                print(cmd)
                subprocess.Popen(cmd, shell=True)
                time.sleep(1)

            # just to enable 0-RTT, not for performance measurements
            if implementation == Implementation.PICOQUIC and False:
                for operator in operators:
                    sshRemoteLogin = operators[operator]['sshRemoteLogin']
                    destIp = operators[operator]['destIp']
                    runPicoquicClient(sshRemoteLogin=sshRemoteLogin, ccAlgorithm=ccAlgorithm, destIp=destIp, destPort=4431, objsize=1000)
                    waitForQlogFile(temp_qlog_dir)
                    subprocess.run(f"mv temp_qlog/*.qlog {results_dir}/picoquic_{operator}_{ccAlgorithm}_initial.qlog", shell=True)

            print(f"\n\n\nRunning measurements with varying object sizes")

            for objsize in objsizeList:
                if (objsize == int(100e6) and iteration > 5) or (objsize == int(300e6) and iteration > 2):
                    print(f"Skipping very large objects in iteration {iteration}")
                else:
                    for operator in operators:
                        sshRemoteLogin = operators[operator]['sshRemoteLogin']
                        destIp = operators[operator]['destIp']

                        if implementation == Implementation.PICOQUIC:
                            currentSetup = f"picoquic_{operator}_{ccAlgorithm}_objsize{objsize}_iter{iteration}"
                            print(f"\n\n\nRunning {currentSetup}\n\n\n")
                            runPicoquicClient(sshRemoteLogin=sshRemoteLogin, ccAlgorithm=ccAlgorithm, destIp=destIp, destPort=4431, objsize=objsize)
                            waitForQlogFile(temp_qlog_dir)
                            subprocess.run(f"mv {temp_qlog_dir}/*.qlog {results_dir}/{currentSetup}.qlog", shell=True)

                        if implementation == Implementation.QUICHE:
                            currentSetup = f"quiche_{operator}_{ccAlgorithm}_objsize{objsize}_iter{iteration}"
                            print(f"\n\n\nRunning {currentSetup}")
                            runQuicheClient(sshRemoteLogin=sshRemoteLogin, ccAlgorithm=ccAlgorithm, destIp=destIp, destPort=4432, objsize=objsize)
                            time.sleep(3)
                            subprocess.run(f"mv {temp_qlog_dir}/*.sqlog {results_dir}/{currentSetup}.sqlog", shell=True)

            #kill server
            if implementation == Implementation.PICOQUIC:
                subprocess.run("pkill picoquicdemo".split())
            if implementation == Implementation.QUICHE:
                subprocess.run("pkill quiche-server".split())
            time.sleep(1)


def evalPicoquicSingleFile(filename):
    parameters = os.path.basename(filename).replace(".qlog", "").split(sep="_")
    print(parameters)
    operator = parameters[1]
    cc = parameters[2]
    objsize = int(parameters[3].replace("objsize", ""))
    iteration = int(parameters[4].replace("iter", ""))

    metrics_list = []

    with open(filename, 'r') as json_file_read:
        json_file_load = json.load(json_file_read)
    # Parsing qlog (json) file
    events = json_file_load["traces"][0]["events"]

    for event in events:
        if event[1] == 'recovery' and event[2] == 'metrics_updated':
            #print(event)
            for key in event[3]:
                #print(f"time {event[0]}, key {key}, value {event[3][key]}")
                metric_dict = {'operator': operator,
                               'cc': cc,
                               'objsize': objsize,
                               'iteration': iteration,
                               'time': event[0],
                               'key': key,
                               'value': int(event[3][key])}
                metrics_list.append(metric_dict)
    return metrics_list

def evalQuicheSingleFile(filename):
    parameters = os.path.basename(filename).replace(".sqlog", "").split(sep="_")
    operator = parameters[1]
    cc = parameters[2]
    objsize = int(parameters[3].replace("objsize", ""))
    iteration = int(parameters[4].replace("iter", ""))

    metrics_list = []

    with open(f'{filename}', 'r') as json_file_read:
        content = json_file_read.read()
        # split the input data into individual JSON texts
        # \u001E is the ASCII Record Separator (RS) character
        json_objects = content.split('\u001E')
        for json_object in json_objects:
            # remove the line feed at the end of the json_text
            json_object = json_object.strip()
            if json_object:  # check the string is not empty
                try:
                    json_seq = json.loads(json_object)

                    if json_seq.get('name') == 'recovery:metrics_updated':
                        for key in json_seq['data']:
                            metric_dict = {'operator': operator,
                                            'cc': cc,
                                            'objsize': objsize,
                                            'iteration': iteration,
                                            'time': json_seq['time'] * 1000,
                                           'key': key,
                                           'value': json_seq['data'][key] * 1000 if key in ["min_rtt", "smoothed_rtt",
                                                                                            "latest_rtt",
                                                                                            "rtt_variance"] else
                                           json_seq['data'][key]}
                            metrics_list.append(metric_dict)

                except json.JSONDecodeError:
                    print(f'Skipping malformed JSON object: {json_object}...')
    return metrics_list


def evalPicoquicMeasAndWriteToCsv(path2files):
    inputFiles = glob.glob(f"{path2files}/*.qlog")

    if not inputFiles:
        return

    metrics_list = []
    for inputFile in inputFiles:
        print(f"evalPicoquicMeasAndWriteToCsv() {inputFile}")
        metrics_list.extend(evalPicoquicSingleFile(inputFile))
    df = pd.DataFrame(metrics_list)
    df.to_csv("data_picoquic.csv")
    print("Saved data_picoquic.csv")

def evalQuicheMeasAndWriteToCsv(path2files):
    inputFiles = glob.glob(f"{path2files}/*.sqlog")

    if not inputFiles:
        return

    metrics_list = []
    for inputFile in inputFiles:
        print(f"evalQuicheMeasAndWriteToCsv() {inputFile}")
        metrics_list.extend(evalQuicheSingleFile(inputFile))
    df = pd.DataFrame(metrics_list)
    df.to_csv("data_quiche.csv")
    print("Saved data_quiche.csv")


def readCsvAndPlot(filename):
    print(f"Reading {filename}")
    df = pd.read_csv(filename)

    print("Start plotting")
    operators = ["NetEm", "Skydsl", "Konnect", "Starlink"] # FIXME global variable is overwritten just for plotting
    ccs = ["cubic", "bbr"]

    if False:
        # some statistics
        for operator in operators:
            for cc in ccs:
                for objsize in objsizeList:
                    #print(df)
                    latest_rtts = df.query('operator == @operator and cc == @cc and objsize == @objsize and key == "latest_rtt"')['value']
                    min_rtts = df.query('operator == @operator and cc == @cc and objsize == @objsize and key == "min_rtt"')['value']
                    print(f"Operator {operator}, cc {cc}, objsize {objsize}:   ", end="")
                    if not latest_rtts.empty:
                        print(f"{len(latest_rtts)}*latest_rtt ({min(latest_rtts)}/{np.median(latest_rtts)}/{max(latest_rtts)})   ", end="")
                    if not min_rtts.empty:
                        print(f"{len(min_rtts)}*min_rtt ({min(min_rtts)}/{np.median(latest_rtts)}/{max(min_rtts)})", end="")
                    print("")


    # plot RTTs
    fig, axes = plt.subplots(2, 4, figsize=(4*7,2*5))
    for idxColumnOperator, operator in enumerate(operators):
        for idxRowCc, cc in enumerate(ccs):
            dfTemp = df.query('operator == @operator and cc == @cc and (key == "latest_rtt" or key == "min_rtt")')
            dfTemp['objsize'] /= 1000000 # byte -> Mbyte
            dfTemp['value'] /= 1000 # us -> ms
            (sns.boxplot(ax=axes[idxRowCc][idxColumnOperator],
                           data=dfTemp, x="objsize", y="value", hue="key")
             .set(title=f"Operator {operator}, Congestion Control {cc.upper()}", xlabel="Object Size [Mbyte]", ylabel="RTT [ms]"))
            if operator == "Starlink":
                ylim = 2e2
            else:
                ylim = 2e3
            axes[idxRowCc][idxColumnOperator].set_ylim(0, ylim)
    fig.autofmt_xdate(rotation=45)
    fig.tight_layout()
    plt.savefig("boxplot_RTTs.png")

    # plot cwnd and bytes_in_flight
    fig, axes = plt.subplots(2, 4, figsize=(4*7,2*5))
    plt.xticks(rotation=45)
    for idxColumnOperator, operator in enumerate(operators):
        for idxRowCc, cc in enumerate(ccs):
            dfTemp = df.query('operator == @operator and cc == @cc and (key == "bytes_in_flight" or key == "cwnd" or key == "congestion_window")')
            dfTemp['objsize'] /= 1000000 # byte -> Mbyte
            dfTemp['value'] /= 1000 # bytes -> kbyte
            (sns.boxplot(ax=axes[idxRowCc][idxColumnOperator],
                           data=dfTemp, x="objsize", y="value", hue="key")
             .set(title=f"Operator {operator}, Congestion Control {cc.upper()}", xlabel="Object Size [Mbyte]", ylabel="[kbyte]"))
            axes[idxRowCc][idxColumnOperator].set_yscale('log')
    fig.autofmt_xdate(rotation=45)
    fig.tight_layout()
    plt.savefig("boxplot_bytesInFlight_cwnd.png")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--runPicoquicMeas", action='store_true')
    parser.add_argument("--runQuicheMeas", action='store_true')
    parser.add_argument("--evalQlogFilesAndWriteToCsv", type=str)
    parser.add_argument("--readCsvAndPlot", action='store_true')
    args = parser.parse_args()
    print(args)

    if args.runPicoquicMeas:
        runImplementation(Implementation.PICOQUIC, iterations=10)

    if args.runQuicheMeas:
        runImplementation(Implementation.QUICHE, iterations=10)

    if args.evalQlogFilesAndWriteToCsv:
        evalPicoquicMeasAndWriteToCsv(args.evalQlogFilesAndWriteToCsv)
        evalQuicheMeasAndWriteToCsv(args.evalQlogFilesAndWriteToCsv)

    if args.readCsvAndPlot:
        if os.path.isfile("data_picoquic.csv"):
            readCsvAndPlot("data_picoquic.csv")




