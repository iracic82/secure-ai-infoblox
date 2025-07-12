#! /bin/bash
sudo apt update
sudo apt install -y docker.io
sudo apt-get install -y iperf3
sudo systemctl start docker
sudo systemctl enable docker
sudo groupadd docker
sudo usermod -aG docker linuxuser
sudo curl https://igor-prosimo.s3.eu-west-1.amazonaws.com/network_testing.py -o /home/linuxuser/network_testing.py
sudo curl https://infoblox-igor.s3.eu-west-1.amazonaws.com/app_dns_discovery.py -o /home/ec2-user/app_dns_discovery.py
sudo docker pull iracic82/prosimo-flask-app-labs:latest
sudo docker pull iracic82/prosimo-iperf3:latest
sudo docker pull iracic82/prosimo-postgresql:latest
sudo docker pull iracic82/prosimo-flask-sqlclient:latest
sudo docker pull iracic82/prosimo-security-api:latest
sudo docker run	-d -p 5000:5000	iracic82/prosimo-flask-sqlclient:latest
sudo docker run -d --name iperf-server -p 5201:5201/tcp -p 5201:5201/udp -p 5201:5201/sctp iracic82/prosimo-iperf3:latest -s



cat <<"EOT" > /home/linuxuser/run_script.sh
#!/bin/bash

while true; do
    # Call your Python script here
    python3 /home/linuxuser/app_dns_discovery.py

    # Sleep for 3 minutes (180 seconds)
    sleep 180
done
EOT

sudo chmod +x /home/linuxuser/run_script.sh
sudo chown linuxuser:linuxuser /home/linuxuser/run_script.sh
sudo /home/linuxuser/run_script.sh &
