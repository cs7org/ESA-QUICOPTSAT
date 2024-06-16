#!/bin/bash
set -x

HOST_NAME=(       "Astra"       "Skydsl"      "Konnect"     "Starlink"    "Tooway16"    "NetEm")
HOST_IP=(         "10.188.x.y"  "10.188.x.y"  "10.188.x.y"  "10.188.x.y"  "10.188.x.y"  "10.188.x.y")
DEST_IP=(         "131.188.x.y" "131.188.x.y" "131.188.x.y" "131.188.x.y" "131.188.x.y" "192.168.x.y")
#HOST_ETH=(        "eno1"        "enp3s0f0"    "eno1"        "eno1") #replaced with any, because interface is different for direct and wireguard



for iter in `seq 0 19`; do
  for h in 4; do  # see table above
    for hystart in ""; do # "--disable-hystart"
      SSH="user@${HOST_IP[$h]}"
      LOGFILE="picoquic_${HOST_NAME[$h]}_hystart${hystart}_iter${iter}"

      echo -e "\n\n\n\nRunning $SSH and $LOGFILE"

      ssh $SSH "ping ${DEST_IP[$h]} -c3"

      SSLKEYLOGFILE=temp_log/picoquic.keys \
      ./picoquicdemo -q . -L -l temp_log/${LOGFILE}.textlog -G cubic -1 &
      sleep 3
      ssh $SSH "picoquic/picoquicdemo -G cubic -n xyz ${DEST_IP[$h]} 4443 /$((10*1000*1000))"
      
      while pgrep picoquicdemo > /dev/null; do
      	echo "waiting for picoquicdemo server to finish"
      	sleep 1
      done

      mv *.qlog temp_log/picoquic_${HOST_NAME[$h]}_hystart${hystart}_iter${iter}.qlog
    done
  done
done


# rename.ul '_hystart_' '_hystartDefault_' *.pcap
# rename.ul '_hystart--disable-hystart' '_hystartDisable' *.pcap

