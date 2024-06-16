#!/usr/bin/env python3

import argparse
import numpy as np
import glob
import re
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import dateutil

sns.set_theme()

customSort = {'Konnect': 1, 'Skydsl': 2, 'Astra': 3, 'Tooway': 4, 'NetEm': 5, "Starlink": 6}


def evalQuiche():
    inputFiles = glob.glob("data/*.rustlog")
    print(f"Found {len(inputFiles)} files: {inputFiles}")

    res = []
    for file in inputFiles:
        print(file)
        inputFileName = file.replace("data/", "").replace(".rustlog", "").split(sep='_')
        operator = inputFileName[-3],
        operator = operator[0]
        iteration = inputFileName[-1].replace("iter", "")

        textRaw = open(file, 'r')

        tsNewConn = None
        tsCss = None
        cwndCss = None
        tsFin = None

        # New connection
        for line in textRaw:
            if re.search(r'New connection.*', line):
                #print(line)
                tsNewConn = re.search(r'\d\d\d\d-\d\d-\d\dT(.*?)Z', line).group(1)
                tsNewConn = dateutil.parser.parse(tsNewConn).timestamp()
                break

        # css_start_time
        for line in textRaw:
            if re.search(r'css_start_time=Some.*', line):
                #print(line)
                tsCss = re.search(r'\d\d\d\d-\d\d-\d\dT(.*?)Z', line).group(1)
                tsCss = dateutil.parser.parse(tsCss).timestamp()
                #print(tsCss)
                cwndCss = re.search(r'cwnd=(.*?)\s', line).group(1)
                break

        # STREAM id=0 fin=true
        for line in textRaw:
            if re.search(r'STREAM id=0 (.*?) fin=true', line):
                tsFin = re.search(r'\d\d\d\d-\d\d-\d\dT(.*?)Z', line).group(1)
                tsFin = dateutil.parser.parse(tsFin).timestamp()
                break

        if tsNewConn and tsCss and cwndCss and tsFin:
            res.append({"Operator": operator,
                        "iteration": iteration,
                        'tsNewConn': tsNewConn,
                        'tsExit': tsCss,
                        'cwndExit': int(cwndCss),
                        'tsFin': tsFin,
                        'time2exit': tsCss - tsNewConn,
                        'time2fin': tsFin - tsNewConn})
        else:
            print(f"Warning - missing data in {file}: "
                  f"tsNewConn {tsNewConn}, tsCss {tsCss}, cwndCss {cwndCss}, tsFin {tsFin}")

    df = pd.DataFrame(res)
    # https://stackoverflow.com/questions/13838405/custom-sorting-in-pandas-dataframe
    df.sort_values(by=['Operator'], key=lambda x: x.map(customSort), inplace=True)
    print(len(df))
    print(df)

    labelTime = "Time [s] between initial packet and\nfirst css_start_time"
    labelCwnd = "cwnd [bytes] at first css_start_time"

    # scatterplot
    fig, axes = plt.subplots()
    sns.scatterplot(data=df, x="time2exit", y="cwndExit", hue='Operator')
    axes.set(xlabel=labelTime,
                ylabel=labelCwnd)
    fig.tight_layout()
    plt.savefig("scatter_quiche_hystart.pdf")

    # CDFs
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    sns.ecdfplot(ax=axes[0], data=df, x='time2exit', hue='Operator')
    axes[0].set(xlabel=labelTime,
                xlim=(0, 5))

    sns.ecdfplot(ax=axes[1], data=df, x='cwndExit', hue='Operator')
    axes[1].set(xlabel=labelCwnd,
                xlim=(0, 150000))
    axes[1].tick_params('x', labelrotation=45)

    fig.tight_layout()
    plt.savefig("cdf_quiche_hystart++.pdf")




def evalPicoquic(setup):
    print(setup)
    textRaw = open(setup, 'r')

    tsExit = None
    cwndExit = None
    tsFin = np.nan

    # css_start_time
    for line in textRaw:
        if re.search(r'picoquic_hystart_test\sret\s1', line):
            type = "picoquic hystart delay"
            tsExit = re.search(r'picoquic_hystart_test\] (\d+): JOERG picoquic_hystart_test ret 1', line).group(1)
            line = next(textRaw)
            cwndExit = re.search(r'JOERG cwnd after picoquic_hystart_test is (\d+)', line).group(1)
            print(f"hystart_test {tsExit} and {cwndExit}")
            break
        if re.search(r'picoquic_hystart_loss_test\sret\s1', line):
            type = "picoquic hystart loss"
            tsExit = re.search(r'picoquic_hystart_loss_test\] (\d+): JOERG picoquic_hystart_loss_test ret 1', line).group(1)
            line = next(textRaw)
            cwndExit = re.search(r'JOERG cwnd after picoquic_hystart_loss_test is (\d+)', line).group(1)
            print(f"hystart_loss_test {tsExit} and {cwndExit}")
            break

    if tsExit is None:
        return {'type': "not found"}

    return {'type': type,
            'tsExit': tsExit,
            'time2exit': tsExit,
            'cwndExit': cwndExit}




def evalLinuxHystart():
    inputFiles = glob.glob("dmesg_*.dmesg_log")
    #print(f"Found {len(inputFiles)} files: {inputFiles}")

    res = []
    for file in inputFiles:
        print(file)
        operator = file.replace("dmesg_","").split(".")[0]

        textRaw = open(file, 'r')

        tsStart = None
        tsExit = None
        cwndExit = None

        for line in textRaw:
            if re.search(r'HYSTART_DELAY', line):
                tsExit = float(re.search(r'(\d+\.\d+)\] HYSTART_DELAY', line).group(1))
                cwndExit = int(re.search(r'HYSTART_DELAY cwnd (\d+)', line).group(1))
                line = next(textRaw)
                tsStart = float(re.search(r'(\d+\.\d+)\] HYSTART tcp_init_transfer', line).group(1))
                print(f"HYSTART_DELAY {tsExit}-{tsStart}={tsExit-tsStart} and {cwndExit}")
                res.append({"Operator": operator,
                            "tsStart": tsStart,
                            "tsExit": tsExit,
                            "time2exit": tsExit-tsStart,
                            "cwndExit": cwndExit})
            if re.search(r'HYSTART_LOSS', line):
                assert False
                tsExit = re.search(r'\[(\d+)\] HYSTART_DELAY', line).group(1)
                cwndExit = re.search(r'HYSTART_DELAY cwnd (\d+)', line).group(1)
                line = next(textRaw)
                tsStart = re.search(r'\[(\d+)\] HYSTART tcp_init_transfer', line).group(1)
                print(f"HYSTART_DELAY {tsExit} and {cwndExit}")
                break

    df = pd.DataFrame(res)
    # https://stackoverflow.com/questions/13838405/custom-sorting-in-pandas-dataframe
    df.sort_values(by=['Operator'], key=lambda x: x.map(customSort), inplace=True)
    print(len(df))
    print(df)

    labelTime = "Time [s] between tcp_init_transfer and\nHYSTART_DELAY"
    labelCwnd = "cwnd [packets] at HYSTART_DELAY"

    # scatterplot
    fig, axes = plt.subplots()
    sns.scatterplot(data=df, x="time2exit", y="cwndExit", hue='Operator')
    axes.set(xlabel=labelTime,
                ylabel=labelCwnd)
    fig.tight_layout()
    plt.savefig("scatter_linux_hystart.pdf")

    # CDFs
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    sns.ecdfplot(ax=axes[0], data=df, x='time2exit', hue='Operator')
    axes[0].set(xlabel=labelTime,
                xlim=(0, 5))

    sns.ecdfplot(ax=axes[1], data=df, x='cwndExit', hue='Operator')
    axes[1].set(xlabel=labelCwnd,
                xlim=(0, 150))
    axes[1].tick_params('x', labelrotation=45)

    fig.tight_layout()
    plt.savefig("cdf_linux_hystart.pdf")




if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exp", type=str, required=True)
    args = parser.parse_args()

    if args.exp == "quiche":
        evalQuiche()
    elif args.exp == "picoquic":
        evalPicoquic()
    elif args.exp == "linuxHystart":
        evalLinuxHystart()


