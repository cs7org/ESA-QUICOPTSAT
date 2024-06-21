import argparse
import os.path
import time
import json
from glob import glob

import numpy as np

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def process_file_name(file):
    file = os.path.basename(file)
    provider = file.split(".")[0].split("_")[0]
    algorithm = file.split(".")[0].split("_")[2]
    size = file.split(".")[1]

    print(f"file {file}: provider {provider}, size {size}, algorithm {algorithm}")
    return provider, size, algorithm

def size_to_bytes(size):
    units = {'KB': 10 ** 3, 'MB': 10 ** 6, 'GB': 10 ** 9}
    num, unit = int(size[:-2]), size[-2:]
    return num * units[unit]

def process_qlog(qlog_file):
    global df
    provider, size, algorithm = process_file_name(file)

    with open(qlog_file, 'r') as qlog:
        try:
            qlog_loaded = json.load(qlog)
        except:
            print(f"Can't load {qlog_file}")
            return

        # bytesize
        #bytesize = 0
        # for packet in qlog_loaded['traces'][0]['events']:
        #     if packet[1] == 'transport' and packet[2] == 'packet_sent':
        #         for frame in packet[3]['frames']:
        #             if frame['frame_type'] == 'stream':
        #                 bytesize += frame['length']
        bytesize = size_to_bytes(size)

        # duration
        connection_start = qlog_loaded['traces'][0]['events'][0][0]
        connection_end = qlog_loaded['traces'][0]['events'][len(qlog_loaded['traces'][0]['events']) - 2][0]

        df = pd.concat([pd.DataFrame([[provider, algorithm, bytesize, connection_end - connection_start]], columns=df.columns), df],
                       ignore_index=True)

def process_sqlog(sqlog_file):
    global df
    provider, size, algorithm = process_file_name(file)

    with open(sqlog_file, 'r') as qlog:
        for line in qlog:
            if line[0] == '\x1e':
                line = line[1:]
            try:
                qlog_loaded = json.loads(line)
            except:
                print(f"Can't load {sqlog_file}")
                return

            # bytesize
            bytesize = size_to_bytes(size)

            # duration
            if "name" in qlog_loaded:
                if qlog_loaded['name'] == "transport:packet_received":
                    for frames in qlog_loaded['data']['frames']:
                        if frames['frame_type'] == "connection_close":
                            connection_end = qlog_loaded['time']

    # TODO
    connection_start = 0

    df = pd.concat([pd.DataFrame(
        [[provider, algorithm, bytesize, int((connection_end - connection_start) * 1000)]], columns=df.columns),
                    df],
                   ignore_index=True)


# Define pandas dataframe
df = pd.DataFrame(columns=['Provider', 'Type', 'Object size', 'Duration'])

# Reading files from input
parser = argparse.ArgumentParser(
    description='Process qlog files and generate visualizations.')
parser.add_argument(
    'file',
    nargs='+',
    type=str,
    help='List of qlog files to process')
args = parser.parse_args()
files = []

for arg in args.file:
    files += glob(arg)

# Process files
for file in files:
    ext = os.path.splitext(file)[1]
    if ext == ".qlog":
        process_qlog(file)
    elif ext == ".sqlog":
        process_sqlog(file)

df = df.sort_values(by='Type', ascending=True)
df['Duration'] /= 1e6 # us to s

print("Dataframe:")
print(df)

# Plot
sns.set()
ax = sns.lineplot(x='Object size', y='Duration', hue='Type', data=df, errorbar='sd')
plt.xticks(range(0, 10000001, 1000000), ['0MB', '1MB', '2MB', '3MB', '4MB', '5MB', '6MB', '7MB', '8MB', '9MB', '10MB'])
plt.ylim(bottom=0)
plt.ylabel('Duration (s)')
plt.title(df['Provider'][0])
plt.show()

df.to_csv("careful_resume_plots.csv")

plt.savefig("results.png")

