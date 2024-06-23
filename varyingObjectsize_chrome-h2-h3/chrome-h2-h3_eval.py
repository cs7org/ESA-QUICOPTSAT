import argparse
import os.path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


# csv files are expected to be in the format "result_provider_protocol.csv"
#                                      e.g., "result_starlink_quic.csv"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('csv_files', nargs='+', type=str,
                        help='List of csv files to process')
    args = parser.parse_args()

    df = pd.DataFrame()

    for file in args.csv_files:
        print(file)

        fileBasename = os.path.basename(file)
        operator = fileBasename.split("_")[1]
        protocol = fileBasename.split("_")[2]

        df_temp = pd.read_csv(file)
        df  = pd.concat([df, df_temp]) #concat is slow but I don't care
    #print(df)

    df.replace("netem-matthias", "NetEm (50/5)", inplace=True)
    df.replace("p700skydsl", "SkyDSL (50/5)", inplace=True)
    df.replace("op9020konnect", "Konnect (50/5)", inplace=True)
    df.replace("op9020starlink", "Starlink", inplace=True)
    df.replace("telekom5g", "Telekom 5G", inplace=True)
    df.replace("quic", "QUIC", inplace=True)
    df.replace("tcp", "TCP", inplace=True)
    df['Size'] /= 1000   #object size kbyte -> Mbyte
    df['Duration'] /= 1000 #duration ms -> s

    customSort = {"NetEm (50/5)": 0,
                  "Konnect (50/5)": 1,
                  "SkyDSL (50/5)": 2,
                  "Starlink": 3,
                  "Telekom5G": 4}
    df.sort_values(by="Operator", inplace=True, key=lambda x: x.map(customSort))
    df.to_csv("result.csv")
    #print(df)

    # plot
    sns.set_theme()
    sns.lineplot(data=df, x='Size', y='Duration', hue='Operator', style='Protocol',
                 estimator="median", errorbar=("pi", 50))
    plt.xlabel("Object size [Mbyte]")
    plt.ylabel("Page Load Time (duration) [s]")
    plt.savefig("result.png")
