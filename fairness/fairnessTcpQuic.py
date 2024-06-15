import argparse
import subprocess
import time
import socket
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

import matplotlib
matplotlib.rcParams['pdf.fonttype'] = 42
matplotlib.rcParams['ps.fonttype'] = 42

sns.set_theme()


### Run fairness / competing traffic tests
#
# QUIC ... QUICvsTCP ... TCP
#
# TCP ... TCPvsQUIC ... QUIC


### Topology ###
#
# iperf/quic server ------------ NetEm ------------ iperf/quic client
#                                50 Mbit/s
#                                300ms
#                                buffer 1 BDP
#
# Script is run on server, connects to clients, data is sent from server to client


### Prerequisites ###
# ssh to remote PC (see sshLogin below) without password
# sudo without password in local and remote PC: tcpdump, sysctl, pkill


operators = {"NetEm":  {"sshLogin": "user@netem",  "serverIp": "192.168.x.y", "localEth": "enp1s0f0", "remoteEth": "eno1"},
             "SkyDSL": {"sshLogin": "user@skydsl", "serverIp": "192.168.x.y", "localEth": "enp1s0f0", "remoteEth": "eno1"}
             # add further operators as needed
             }


def runMeas(scenario):
    for opKey in operators:
        ssh = f"ssh {operators[opKey]['sshLogin']} "
        serverIp = operators[opKey]['serverIp']
        localEth = operators[opKey]['localEth']
        remoteEth = operators[opKey]['remoteEth']

        setupName = f"fairnessTcpQuic_{opKey}_{scenario}"
        print(f"Starting {setupName}")

        #start tcpdump
        subprocess.Popen(f"sudo tcpdump -i {localEth} -s 100 -w {setupName}_sender.pcap tcp port 5001 or udp port 4443".split())
        subprocess.Popen(ssh.split() + [f"sudo tcpdump -i {remoteEth} -s 100 -w {setupName}_receiver.pcap tcp port 5001 or udp port 4443"])
        time.sleep(1)

        #start servers
        subprocess.Popen(f"iperf -s -i 0.5 --enhanced --reportstyle C --output {setupName}_iperf-sender.csv", shell=True)

        subprocess.run("rm -rf picoquic/temp_qlog && mkdir picoquic/temp_qlog", shell=True)
        subprocess.Popen(f"cd picoquic && ./picoquicdemo -q temp_qlog -G cubic -1", shell=True)
        time.sleep(1)

        #run clients
        if scenario == "tcpThenQuic":
            subprocess.Popen(ssh.split() + [f"iperf -c {serverIp} -i 0.5 --enhanced --reportstyle C --reverse --time 100 --output {setupName}_iperf-receiver.csv"])
            time.sleep(50)
            subprocess.run(ssh.split() + [f"picoquic/picoquicdemo -n xyz -G cubic {serverIp} 4443 /450000000"])
        elif scenario == "quicThenTcp":
            subprocess.Popen(ssh.split() + [f"picoquic/picoquicdemo -n xyz -G cubic {serverIp} 4443 /450000000"])
            time.sleep(50)
            subprocess.run(ssh.split() + [f"iperf -c {serverIp} -i 0.5 --enhanced --reportstyle C --reverse --time 100 --output {setupName}_iperf-receiver.csv"])
        else:
            assert False, "wrong setup"

        #kill tcpdump
        time.sleep(30)
        subprocess.run("sudo pkill iperf".split())
        subprocess.run("sudo pkill tcpdump".split())
        subprocess.run(ssh.split() + ["sudo pkill tcpdump"])
        time.sleep(1)

        subprocess.run(f"mv picoquic/temp_qlog/*.qlog {setupName}.qlog", shell=True)
        subprocess.run(f"scp {operators[opKey]['sshLogin']}:~/fairnessTcpQuic_* .", shell=True)
        subprocess.run(ssh.split() + ["rm -f fairnessTcpQuic_*"])

        print(f"Finished {setupName}\n\n\n\n\n")


def eval(setupName):
    print(f"\n\n\nRunning {setupName}\n\n\n")

    if True:
        subprocess.run(f"echo \"time,conv,seq\" > {setupName}_sender_tcptrace.csv", shell=True)
        subprocess.run(f"tshark -r {setupName}_sender.pcap -Y \"tcp.srcport == 5001\" -T fields -e frame.time_relative -e tcp.stream -e tcp.seq -E separator=, >> {setupName}_sender_tcptrace.csv", shell=True)

    dfSeq = pd.read_csv(f"{setupName}_sender_tcptrace.csv")
    dfSeq["seq"] /= 1000000 # seq number in Mbyte

    # https://sourceforge.net/p/iperf2/code/ci/master/tree/src/ReportOutputs.c
    csvRxHeader = ["date", "destIp", "destPort", "srcIp", "srcPort", "transferID",
                   "timeInterval", "bytes", "goodput",
                   "readCnt", "read0", "read1", "read2", "read3", "read4", "read5", "read6", "read7",
                   "dummy0", "dummy1", "dummy2"]
    csvTxHeader = ["date", "destIp", "destPort", "srcIp", "srcPort", "transferID",
                   "timeInterval", "bytes", "goodput",
                   "writeCnt", "writeErr", "retry", "cwnd", "rtt", "rttvar",
                   "dummy0", "dummy1", "dummy2"]

    dfTx = pd.read_csv(f"{setupName}_iperf-sender.csv", names=csvTxHeader, header=None)

    dfTx.drop(dfTx.tail(1).index, inplace=True)  # remove last (summary) line
    dfTx.insert(0, "interval", [i/2 for i in range(1, len(dfTx)+1)])  # make numeric intervals

    if "quicThenTcp" in setupName:
        dfTx['interval'] += 50

    #print(dfTx)
    dfTx['cwnd'] /= 1000
    dfTx['rtt'] /= 1e3
    dfTx['goodput'] /= 1000000

    font_size = 10

    fig, axes = plt.subplots(5, 1, figsize=(4, 10), sharex=True)
    for axis in axes:
        axis.set_xlim(0,150)

    sns.scatterplot(ax=axes[0], data=dfSeq, size=0.05, x="time", y="seq")
    axes[0].set_ylabel('Seq. number [MB]', fontsize=font_size)
    axes[0].legend([], [], frameon=False)

    sns.lineplot(ax=axes[1], data=dfTx, x="interval", y="retry")
    axes[1].set_ylabel('Retransmissions [count]', fontsize=font_size)

    sns.lineplot(ax=axes[2], data=dfTx, x="interval", y="cwnd")
    axes[2].set_ylabel('Cwnd', fontsize=font_size)

    sns.lineplot(ax=axes[3], data=dfTx, x="interval", y="rtt")
    axes[3].set_ylabel('RTT [ms]', fontsize=font_size)

    sns.lineplot(ax=axes[4], data=dfTx, x="interval", y="goodput")
    axes[4].set_ylabel('Goodput [Mbit/s]', fontsize=font_size)
    axes[4].set_xlabel("Time [s]", fontsize=font_size)

    fig.suptitle(f"{setupName}", fontsize=font_size)

    fig.tight_layout()
    plt.savefig(f"{setupName}_tcp", dpi=600)




if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--runMeas', action='store_true', default=False, help='runMeas')
    parser.add_argument('--eval', action='store_true', default=False, help='runMeas')
    args = parser.parse_args()

    assert (args.runMeas and not args.eval) or (not args.runMeas and args.eval)

    if args.runMeas:
        runMeas(scenario = "tcpThenQuic")
        time.sleep(10)
        runMeas(scenario = "quicThenTcp")

    if args.eval:
        eval("fairnessTcpQuic_NetEm_tcpThenQuic")
        eval("fairnessTcpQuic_NetEm_quicThenTcp")
        eval("fairnessTcpQuic_SkyDSL_tcpThenQuic")
        eval("fairnessTcpQuic_SkyDSL_quicThenTcp")

