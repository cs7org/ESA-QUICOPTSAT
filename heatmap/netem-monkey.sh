#!/bin/bash

# NetEm topology with a quad-port Ethernet card and cabling like mad monkeys would do it
#
# nsClient             nsBridge             nsServer
# enp3s0f0 ---- enp3s0f1 ---- enp4s0f0 ---- enp4s0f1
# 10.3.0.2      10.3.0.1      10.4.0.1      10.4.0.2
# iperf3 -c                                 iperf3 -s                                   

ethClient="enp3s0f0"
ethBridge1="enp3s0f1"
ethBridge2="enp4s0f0"
ethServer="enp4s0f1"

# http://redsymbol.net/articles/unofficial-bash-strict-mode/
# https://github.com/guettli/bash-strict-mode
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
    echo "Script must be run as root user (e.g. via sudo)" >&2
    exit 1
fi


sysctl -w net.ipv4.ip_forward=1

# disabling offloading might avoid problems (and seems to give more accurate buffering delays)
ethtool -K $ethClient  gro off tso off gso off
ethtool -K $ethBridge1 gro off tso off gso off
ethtool -K $ethBridge2 gro off tso off gso off
ethtool -K $ethServer  gro off tso off gso off

ip netns add nsClient
ip netns add nsServer
ip netns add nsBridge

ip link set $ethClient  netns nsClient
ip link set $ethBridge1 netns nsBridge
ip link set $ethBridge2 netns nsBridge
ip link set $ethServer  netns nsServer

ip netns exec nsClient ip addr add 10.3.0.2/24 dev $ethClient
ip netns exec nsBridge ip addr add 10.3.0.1/24 dev $ethBridge1
ip netns exec nsBridge ip addr add 10.4.0.1/24 dev $ethBridge2
ip netns exec nsServer ip addr add 10.4.0.2/24 dev $ethServer

ip netns exec nsClient ip link set dev $ethClient  up
ip netns exec nsBridge ip link set dev $ethBridge1 up
ip netns exec nsBridge ip link set dev $ethBridge2 up
ip netns exec nsServer ip link set dev $ethServer  up

ip netns exec nsClient ip route add 10.4.0.0/24 via 10.3.0.1
ip netns exec nsServer ip route add 10.3.0.0/24 via 10.4.0.1


# config based on Martin's seminal NetEm insights
# 1*BDP FL: 50 Mbit/s * 0.6 s = 3.75 Mbyte --> 3.75 Mbyte / 1500 byte = 2500 packets
# 1*BDP RL:                                                              250 packets
# by default, we use a limit of 1*BDP + buffersize = 2*BDP
ip netns exec nsBridge tc qdisc add dev $ethBridge1 root handle 1:0 netem delay 300ms rate 50Mbit limit 5000 #forward link
ip netns exec nsBridge tc qdisc add dev $ethBridge2 root handle 1:0 netem delay 300ms rate  5Mbit limit  500 #return link

echo "Increasing net.ipv4.tcp_wmem and net.ipv4.tcp_rmem to max 50 Mbyte (needed for TCP and high BDP paths)"
for ns in "nsClient" "nsServer"; do
  ip netns exec $ns sysctl -w net.ipv4.tcp_wmem="4096 131072 50000000"
  ip netns exec $ns sysctl -w net.ipv4.tcp_rmem="4096 131072 50000000"
done

echo "Increasing net.core.rmem_max and net.core.rmem_default to 200 Mbyte (needed for UDP to send large CR jumps)"
sysctl -w net.core.rmem_max=200000000
sysctl -w net.core.rmem_default=200000000


# Some tests...
echo "Starting ping test"
ip netns exec nsClient ping 10.4.0.2 -c5
ip netns exec nsServer ping 10.3.0.2 -c5
echo -e "Finished ping test\n\n"

if command -v iperf3 &> /dev/null; then
  echo "Starting iperf3 return link test, server receive goodput (wait until the end) should show ~5 Mbit/s"
  ip netns exec nsServer iperf3 -s --one-off > /dev/null &
  ip netns exec nsClient iperf3 -c 10.4.0.2 --time 5 --udp --bandwidth 5M --get-server-output #return link
  echo -e "Finished iperf3 return link test\n\n"
  sleep 2

  echo "Starting iperf3 return link test, client receive goodput should show ~50 Mbit/s"
  ip netns exec nsServer iperf3 -s --one-off > /dev/null &
  ip netns exec nsClient iperf3 -c 10.4.0.2 --time 5 --udp --bandwidth 50M --reverse   #forward link
  echo "Finished iperf3 forward link test"
else
  echo "iperf3 not found, not running bulk data tests"
fi
