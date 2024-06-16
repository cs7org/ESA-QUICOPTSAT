#!/bin/bash
set -x

HOST_NAME=(       "Astra"       "Skydsl"      "Konnect"     "Starlink"    "Tooway16"    "NetEm")
HOST_IP=(         "10.188.x.y"  "10.188.x.y"  "10.188.x.y"  "10.188.x.y"  "10.188.x.y"  "10.188.x.y")
DEST_IP=(         "131.188.x.y" "131.188.x.y" "131.188.x.y" "131.188.x.y" "131.188.x.y" "192.168.x.y")
#HOST_ETH=(        "eno1"        "enp3s0f0"    "eno1"        "eno1") #replaced with any, because interface is different for direct and wireguard



for iter in `seq 0 0`; do
  for file in "1M"; do #"1M" "10M" "100M"; do
    for h in 4; do #0 1 2 3 4; do # see table above
      for hystart in ""; do # "--disable-hystart"; do
        for cc in "cubic"; do #"cubic" "bbr" "bbr2"; do
          for pacing in "" "--disable-pacing"; do
            SSH="user@${HOST_IP[$h]}"
            LOGFILE="quiche_${HOST_NAME[$h]}_file${file}_cc${cc}_hystart${hystart}_pacing${pacing}_iter${iter}"
            mkdir $LOGFILE

            echo -e "\n\n\n\nRunning $SSH and $LOGFILE"

            ssh $SSH "ping ${DEST_IP[$h]} -c3"

            RUST_LOG=trace \
            SSLKEYLOGFILE=${LOGFILE}/server.keys \
            QLOGDIR=${LOGFILE} \
            ./quiche/target/debug/quiche-server --cc-algorithm ${cc} ${hystart} ${pacing} --cert ./quiche/apps/src/bin/cert.crt --key ./quiche/apps/src/bin/cert.key --root /var/www/html --listen 0.0.0.0:4433 &> ${LOGFILE}/server.rustlog &
          sleep 5  # must be large enough, sleep 1 is not enough and messes up timing
          
            ssh $SSH "mkdir ${LOGFILE}"
            ssh $SSH "RUST_LOG=trace SSLKEYLOGFILE=${LOGFILE}/client.keys QLOGDIR=${LOGFILE} quiche_target/debug/quiche-client --cc-algorithm ${cc} ${hystart} --no-verify https://${DEST_IP[$h]}:4433/file${file}.bin > /dev/null 2> ${LOGFILE}/client.rustlog"
            sleep 3

          done
        done
      done
    done
  done
done


# rename.ul '_hystart_' '_hystartDefault_' *.pcap
# rename.ul '_hystart--disable-hystart' '_hystartDisable' *.pcap

