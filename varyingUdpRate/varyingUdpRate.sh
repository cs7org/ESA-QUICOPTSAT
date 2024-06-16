#!/bin/bash

# Script starts
#  - tcpdump and iperf3 server on DFN university network interface (default namespace)
#  - tcpdump and iperf3 client on St(arlink) namespace/interface
#  - tcpdump and iperf3 client on Ko(nnect) namespace/interface
#  - tcpdump and iperf3 client on As(tra) namespace/interface

# requires: iperf3, tcpdump, parallel

# file name syntax of output files is important for later evaluation script 😬


TIME=$((1*30))
DEST_IP="131.188.x.y"

AS_RL=("500k" "1000k" "1900k" "2000k" "2100k" "2500k")
AS_FL=("5M"   "10M"   "19M"   "20M"   "21M"   "25M")

SK_RL=("1000k" "2000k" "3000k" "4000k" "5000k" "6000k")
SK_FL=("10M"   "30M"   "40M"   "45M"   "50M"   "55M")

KO_RL=("1000k" "2000k" "3000k" "4000k" "5000k" "6000k")
KO_FL=("10M"   "30M"   "40M"   "45M"   "50M"   "55M")

ST_RL=("2000k" "5000k" "10000k" "15000k" "20000k" "25000k")
ST_FL=("10M"   "30M"   "50M"    "100M"   "200M"   "300M")


for i in 0 1 2 3 4 5; do
  echo "Running UDP rate set $i, return link"

  sudo tcpdump -i eno1 -w starlink_rl_rate${ST_RL[$i]}.fau.pcap udp port 5201 &
  sudo tcpdump -i eno1 -w konnect_rl_rate${KO_RL[$i]}.fau.pcap  udp port 5202 &
  sudo tcpdump -i eno1 -w astra_rl_rate${AS_RL[$i]}.fau.pcap    udp port 5203 &
  sudo tcpdump -i eno1 -w skydsl_rl_rate${SK_RL[$i]}.fau.pcap   udp port 5204 &

  sudo ip netns exec nsSt tcpdump -i ens1f0 udp port 5201 -w starlink_rl_rate${ST_RL[$i]}.sat.pcap &
  sudo ip netns exec nsKo tcpdump -i ens1f1 udp port 5202 -w konnect_rl_rate${KO_RL[$i]}.sat.pcap  &
  sudo ip netns exec nsAs tcpdump -i eth4   udp port 5203 -w astra_rl_rate${AS_RL[$i]}.sat.pcap    &
  sudo ip netns exec nsSk tcpdump -i eth5   udp port 5204 -w skydsl_rl_rate${SK_RL[$i]}.sat.pcap   &

  #UDP
  iperf3 -s -i1 -p 5201 &> starlink_rl_rate${ST_RL[$i]}.fau.iperf &
  iperf3 -s -i1 -p 5202 &> konnect_rl_rate${KO_RL[$i]}.fau.iperf  &
  iperf3 -s -i1 -p 5203 &> astra_rl_rate${AS_RL[$i]}.fau.iperf    &
  iperf3 -s -i1 -p 5204 &> skydsl_rl_rate${SK_RL[$i]}.fau.iperf   &

  # wait for tcpdump and iperf to start
  sleep 2

  sudo ip netns exec nsSt iperf3 --udp -c ${DEST_IP} -i1 -p 5201 --udp-counters-64bit --length 1000 --bitrate ${ST_RL[$i]} --time $TIME &> starlink_rl_rate${ST_RL[$i]}.sat.iperf 
  sudo ip netns exec nsKo iperf3 --udp -c ${DEST_IP} -i1 -p 5202 --udp-counters-64bit --length 1000 --bitrate ${KO_RL[$i]} --time $TIME &> konnect_rl_rate${KO_RL[$i]}.sat.iperf  
  sudo ip netns exec nsAs iperf3 --udp -c ${DEST_IP} -i1 -p 5203 --udp-counters-64bit --length 1000 --bitrate ${AS_RL[$i]} --time $TIME &> astra_rl_rate${AS_RL[$i]}.sat.iperf    
  sudo ip netns exec nsSk iperf3 --udp -c ${DEST_IP} -i1 -p 5204 --udp-counters-64bit --length 1000 --bitrate ${SK_RL[$i]} --time $TIME &> skydsl_rl_rate${SK_RL[$i]}.sat.iperf   
  sleep $(($TIME+5))

  echo "Kill tcpdump and iperf3 and exit"
  sudo killall tcpdump
  sudo killall iperf3
  sleep 2
  
  
  
  echo "Running UDP rate set $i, forward link"

  sudo tcpdump -i eno1 -w starlink_fl_rate${ST_FL[$i]}.fau.pcap udp port 5201 &
  sudo tcpdump -i eno1 -w konnect_fl_rate${KO_FL[$i]}.fau.pcap  udp port 5202 &
  sudo tcpdump -i eno1 -w astra_fl_rate${AS_FL[$i]}.fau.pcap    udp port 5203 &
  sudo tcpdump -i eno1 -w skydsl_fl_rate${SK_FL[$i]}.fau.pcap   udp port 5204 &

  sudo ip netns exec nsSt tcpdump -i ens1f0 udp port 5201 -w starlink_fl_rate${ST_FL[$i]}.sat.pcap &
  sudo ip netns exec nsKo tcpdump -i ens1f1 udp port 5202 -w konnect_fl_rate${KO_FL[$i]}.sat.pcap  &
  sudo ip netns exec nsAs tcpdump -i eth4   udp port 5203 -w astra_fl_rate${AS_FL[$i]}.sat.pcap    &
  sudo ip netns exec nsSk tcpdump -i eth5   udp port 5204 -w skydsl_fl_rate${SK_FL[$i]}.sat.pcap   &

  #UDP
  iperf3 -s -i1 -p 5201 &> starlink_fl_rate${ST_FL[$i]}.fau.iperf &
  iperf3 -s -i1 -p 5202 &> konnect_fl_rate${KO_FL[$i]}.fau.iperf  &
  iperf3 -s -i1 -p 5203 &> astra_fl_rate${AS_FL[$i]}.fau.iperf    &
  iperf3 -s -i1 -p 5204 &> skydsl_fl_rate${SK_FL[$i]}.fau.iperf   &

  # wait for tcpdump and iperf to start
  sleep 2

  sudo ip netns exec nsSt iperf3 --udp -c ${DEST_IP} -i1 -p 5201 --udp-counters-64bit --length 1000 --bitrate ${ST_FL[$i]} --reverse --time $TIME &> starlink_fl_rate${ST_FL[$i]}.sat.iperf 
  sudo ip netns exec nsKo iperf3 --udp -c ${DEST_IP} -i1 -p 5202 --udp-counters-64bit --length 1000 --bitrate ${KO_FL[$i]} --reverse --time $TIME &> konnect_fl_rate${KO_FL[$i]}.sat.iperf  
  sudo ip netns exec nsAs iperf3 --udp -c ${DEST_IP} -i1 -p 5203 --udp-counters-64bit --length 1000 --bitrate ${AS_FL[$i]} --reverse --time $TIME &> astra_fl_rate${AS_FL[$i]}.sat.iperf    
  sudo ip netns exec nsSk iperf3 --udp -c ${DEST_IP} -i1 -p 5204 --udp-counters-64bit --length 1000 --bitrate ${SK_FL[$i]} --reverse --time $TIME &> skydsl_fl_rate${SK_FL[$i]}.sat.iperf   
  sleep $(($TIME+5))

  echo "Kill tcpdump and iperf3 and exit"
  sudo killall tcpdump
  sudo killall iperf3
  sleep 2
done



# https://superuser.com/questions/1135733/gnu-parallel-remove-escape-before-space-characters-in-command
#parallel --jobs 0 eval sudo ip netns exec {} ::: \
#  "nsSt iperf3 --udp -c ${DEST_IP} -i1 -p 5201 --udp-counters-64bit --length $PKTLENGTH --bidir --bitrate $BITRATE --time $TIME &> starlink.sat.iperf" \
#  "nsKo iperf3 --udp -c ${DEST_IP} -i1 -p 5202 --udp-counters-64bit --length $PKTLENGTH --bidir --bitrate $BITRATE --time $TIME &> konnect.sat.iperf" \
#  "nsAs iperf3 --udp -c ${DEST_IP} -i1 -p 5203 --udp-counters-64bit --length $PKTLENGTH --bidir --bitrate $BITRATE --time $TIME &> astra.sat.iperf" \
#  "nsSk iperf3 --udp -c ${DEST_IP} -i1 -p 5204 --udp-counters-64bit --length $PKTLENGTH --bidir --bitrate $BITRATE --time $TIME &> skydsl.sat.iperf"

