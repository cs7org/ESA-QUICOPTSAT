import argparse
import subprocess
import multiprocessing
import time
from datetime import datetime
import os
import glob
import re
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# This script requires netem-monkey.sh, a NetEm topology with a quad-port Ethernet card and cabling like mad monkeys would do it
#
# nsClient             nsBridge             nsServer
# enp3s0f0 ---- enp3s0f1 ---- enp4s0f0 ---- enp4s0f1
# 10.3.0.2      10.3.0.1      10.4.0.1      10.4.0.2
# iperf3 -c                                 iperf3 -s

netemBridgeInterfaces = ["enp3s0f1", "enp4s0f0"]
picoquicDir = "./picoquic_cr"
mtuSize = 1300
resultDir = f"results_{datetime.now().strftime('%Y%m%d-%H%M')}/" # raw data will be in subdir "logs"


# returns BDP in bytes
def calculateBdp(datarate_Mbps, delay_ms):
    return int(datarate_Mbps*1e6/8 * delay_ms/1e3)


def setNetem(datarate_Mbps, owd_ms):
    netemBdp = calculateBdp(datarate_Mbps, 2*owd_ms)
    netemBdp = int(netemBdp * 2 / mtuSize) # path+buffer in packets
    
    for dev in netemBridgeInterfaces:
        cmd = f"sudo ip netns exec nsBridge tc qdisc change dev {dev} root handle 1:0 netem delay {owd_ms}ms rate {datarate_Mbps}Mbit limit {netemBdp}"
        print(f"Running {cmd}")
        subprocess.run(cmd.split())
    time.sleep(1)

    subprocess.run("sudo ip netns exec nsClient ping 10.4.0.2 -c3".split())
    subprocess.run("sudo ip netns exec nsServer ping 10.3.0.2 -c3".split())


def runPicoquicServer(datarate, owd, cr):
    stdout = open(f"{resultDir}/logs/rate{datarate}_delay{owd}_server.stdout", "w")
    stderr = open(f"{resultDir}/logs/rate{datarate}_delay{owd}_server.stderr", "w")

    crEnv = ""
    if cr:
        crEnv = f"env PREVIOUS_RTT={int(owd*2*1000)} PREVIOUS_CWND_BYTES={int(calculateBdp(datarate, owd*2))}"
    cmd = f"sudo ip netns exec nsServer {crEnv} {picoquicDir}/picoquicdemo -c {picoquicDir}/certs/cert.pem -k {picoquicDir}/certs/key.pem -q {resultDir} -G cubic -1"
    print(f"Starting picoquic server: {cmd}")
    subprocess.run(cmd.split(), stdout=stdout, stderr=stderr)
    print("Picoquic server finished")

    stdout.close()
    stderr.close()


def runPicoquicClient(datarate, owd, size_bytes):
    stdout = open(f"{resultDir}/logs/rate{datarate}_delay{owd}_client.stdout", "w")
    stderr = open(f"{resultDir}/logs/rate{datarate}_delay{owd}_client.stderr", "w")

    time.sleep(5)  # wait a second until server is ready
    cmd = f"sudo ip netns exec nsClient {picoquicDir}/picoquicdemo -n h3 -q {resultDir} -G cubic 10.4.0.2 4443 /{size_bytes}"
    print(f"Starting picoquic client: {cmd}")
    subprocess.run(cmd, shell=True, stdout=stdout, stderr=stderr)
    print("Picoquic client finished")

    stdout.close()
    stderr.close()


def removeDemoTicketToken():
    for file in ['demo_ticket_store.bin', 'demo_token_store.bin']:
        try:
            os.remove(file)
        except FileNotFoundError:
            pass


def runMeasurements(iterations, cr):
    os.makedirs(f"{resultDir}/logs")

    #for datarate in [10, 25, 50, 75, 100, 150, 200, 250, 300, 350, 400, 450, 500]: # Mbit/s
    #    for owd in [10, 25, 50, 75, 100, 150, 200, 250, 300]: # ms
    for datarate in [10, 25, 50, 100, 200, 250, 500, 1000]:
        for owd in [5, 10, 15, 30, 60, 75, 150, 300]:
            setNetem(datarate, owd)

            #FIXME size of object
            #size = int(datarate * 1e6 / 8 * 1)     # 1-second sized object
            size = 1*calculateBdp(datarate, 2*owd) # 1*BDP-sized object

            for iteration in range(0, iterations):
                p1 = multiprocessing.Process(target=runPicoquicServer, args=[datarate, owd, cr])
                p2 = multiprocessing.Process(target=runPicoquicClient, args=[datarate, owd, size])

                # Start processes and wait for both to finish
                p1.start()
                p2.start()
                p1.join()
                p2.join()

                removeDemoTicketToken()

                # rename files (qlog only contains connection ID) and move qlog files from resultDir to resultDirLogs
                for clientServer in ["server", "client"]:
                    for filePathName in glob.glob(f"{resultDir}/*.{clientServer}.qlog"):
                        newFilename = f"rate{datarate}_delay{owd}_" + os.path.basename(filePathName)
                        os.rename(filePathName, f"{resultDir}/logs/{newFilename}")


def runEval(dirEval, cr):
    df = pd.DataFrame()

    # get duration from client qlog files
    for clientQlogFile in glob.glob(f"{dirEval}/logs/*.client.qlog"):
        print(clientQlogFile)
        pattern = r"rate(\d+)_delay(\d+)_([a-f0-9]+).client.qlog"  # rate200_delay50_obj2s_cr0_52345abd...
        match = re.search(pattern, clientQlogFile)
        datarate = int(match.group(1))
        owd = int(match.group(2))
        connectionid = match.group(3)

        # need to check server file for CR status, doing it this way seems stupid
        serverQlogFile = glob.glob(f"{dirEval}/logs/rate{datarate}_delay{owd}_{connectionid}.*.server.qlog")
        assert len(serverQlogFile) == 1, f"Expected exactly one server .qlog file but found: {serverQlogFile}"
        with open(serverQlogFile[0], "r") as file:
            if "safe_retreat" in file.read():
                crText = "safe_retreat"
            elif cr:
                crText = "enabled"
            else:
                crText = "disabled"

        with open(clientQlogFile, "r") as file:
            for line in file:
                pattern = r"Received (\d+) bytes in ([\d.]+) seconds, ([\d.]+) Mbps."
                match = re.search(pattern, line)
                if match:
                    df_temp = pd.DataFrame([{"Datarate": datarate,
                                             "One-way delay": owd,
                                             "RTT": 2*owd,
                                             "BDP": calculateBdp(datarate, 2 * owd),
                                             "ReportedBytes": match.group(1),
                                             "Connection ID": connectionid,
                                             "Careful Resume": crText,
                                             "Duration": match.group(2),
                                             "Goodput": match.group(3),
                                             "Normalized Goodput": float(match.group(3)) / datarate,
                                             }])
                    df = pd.concat([df, df_temp], ignore_index=True)

    df = df.sort_values(by=["Datarate", "One-way delay"])
    print(df)
    df.to_csv(f'{dirEval}/results.csv', index=False)


def runPlot(filename, cr):
    df = pd.read_csv(filename)

    if cr:
        assert df.query("`Careful Resume` == 'disabled'").empty, "cr flag is set but there are measurements without CR"
        sr = df.query("`Careful Resume` == 'safe_retreat'")
        print(f"{len(sr)} measurements went into Safe Retreat and are discarded for plotting")
        df = df.query("`Careful Resume` == 'enabled'")
    else:
        assert df.query("`Careful Resume` == 'enabled'").empty, "cr flag is not set but there are measurements with CR"

    # Pivot the data using median aggregation
    pivot_table = df.pivot_table(
        index='RTT',
        columns='Datarate',
        values='Normalized Goodput',
        aggfunc='mean'
    )
    pivot_table = pivot_table.sort_index(ascending=False)
    print(pivot_table)

    plt.figure(figsize=(10, 8))
    sns.heatmap(pivot_table, annot=True, fmt=".2f", cmap="viridis", vmin=0, vmax=0.25)
    plt.title(f'Goodput / Link Rate ratio when transferring a BDP-sized object (NetEm with 1 BDP buffer), CR is {"enabled" if cr else "disabled"}.') #FIXME change title when changing object size
    plt.xlabel('Datarate [Mbit/s]')
    plt.ylabel('RTT [ms]')
    plt.tight_layout()

    print(os.path.splitext(filename))
    plt.savefig(os.path.splitext(filename)[0] + ".pdf")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Heatmap fun")
    parser.add_argument('--enableCr', action='store_true', help='Enable Careful Resume')
    args = parser.parse_args()
    print(f"enableCr is {args.enableCr}")

    # Running measurements, evaluation, and plotting: Separate functions to allow
    # separate execution in case one of the steps needs to be re-run afterwards
    runMeasurements(iterations=1, cr=args.enableCr) # results will be in {resultDir}/logs

    runEval(dirEval=resultDir, cr=args.enableCr)

    runPlot(f"{resultDir}/results.csv", cr=args.enableCr)
