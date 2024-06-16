import argparse
import json
import numpy as np
import pandas as pd


def evalSingleFile(filename):
    with open(filename, 'r') as json_file_read:
        json_file_load = json.load(json_file_read)
    # Parsing qlog (json) file
    events = json_file_load["traces"][0]["events"]

    df = pd.DataFrame()
    for event in events:
        if event[1] == 'recovery' and event[2] == 'cr_phase':
            #print(event)
            #print(event[0]) # timestamp
            #print(event[1]) # recovery
            #print(event[2]) # cr_phase
            #print(event[3]) # values (dict)
            temp_df = pd.DataFrame.from_dict(event[3], orient='index').transpose()
            #print(temp_df)
            df = pd.concat([df, temp_df], ignore_index=True)
            #print("print keys...")
            #for key in event[3]:
            #    print(key)
            #    #print(f"time {event[0]}, key {key}, value {event[3][key]}")
            #    metric_dict = {#'operator': operator,
            #                   #'cc': cc,
            #                   #'objsize': objsize,
            #                   #'iteration': iteration,
            #                   'time': event[0],
            #                   'key': key,
            #                   'value': int(event[3][key])}
            #    metrics_list.append(metric_dict)
    #df.mask(df > 10000000000, np.inf, inplace=True)

    if df.empty:
        return df

    df.insert(0,'filename', filename)

    # from picoquic/cc_common.h
    for dfOldNew in ['old', 'new']:
        df[dfOldNew].replace(0, "Observe", inplace=True)
        df[dfOldNew].replace(1, "Recon", inplace=True)
        df[dfOldNew].replace(2, "Unval", inplace=True)
        df[dfOldNew].replace(3, "Validate", inplace=True)
        df[dfOldNew].replace(4, "Retreat", inplace=True)
        df[dfOldNew].replace(100, "Normal", inplace=True)
    if 'trigger' in df.columns:
        df['trigger'].replace(0, "packet_loss", inplace=True)
        df['trigger'].replace(1, "cwnd_limited", inplace=True)
        df['trigger'].replace(2, "cr_mark_ack", inplace=True)
        df['trigger'].replace(3, "rtt_not_val", inplace=True)
        df['trigger'].replace(4, "ECN_CE", inplace=True)
        df['trigger'].replace(5, "exit_recovery", inplace=True)
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Extract CR data from qlog files.')
    parser.add_argument(
        'files',
        nargs='+',
        type=str,
        help='List of qlog files to process')
    args = parser.parse_args()

    df = pd.DataFrame()
    for file in args.files:
        df_temp = evalSingleFile(file)
        if df_temp.empty:
            print(f"file {file} does not have cr_phase")
        else:
            df = pd.concat([df, df_temp])

    print(df)
    df.to_csv("cr.csv")

