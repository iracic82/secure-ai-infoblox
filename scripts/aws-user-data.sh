#! /bin/bash
sudo yum update -y
sudo yum install -y docker
sudo yum install -y iperf3
sudo pip3 install requests
sudo pip3 install urllib3==1.26.15
sudo pip3 install openai
sudo python3 -m pip install dnspython
sudo service docker start
sudo usermod -a -G docker ec2-user
sudo curl https://igor-prosimo.s3.eu-west-1.amazonaws.com/network_testing.py -o /home/ec2-user/network_testing.py
sudo docker pull iracic82/prosimo-flask-app-labs:latest
sudo docker pull iracic82/secure-ai-dns-demo:latest
sudo docker pull iracic82/prosimo-iperf3:latest
sudo docker pull iracic82/prosimo-postgresql:latest
sudo docker pull iracic82/prosimo-flask-sqlclient:latest
sudo docker pull iracic82/prosimo-security-api:latest
sudo docker run -d -p 5000:5000 -e FLASK_SECRET_KEY=supersecurekey9876   -e BEDROCK_REGION=eu-west-2   -e BEDROCK_MODEL_ID=amazon.titan-text-lite-v1   iracic82/secure-ai-dns-demo:latest
sudo docker run -d --name iperf-server -p 5201:5201/tcp -p 5201:5201/udp -p 5201:5201/sctp iracic82/prosimo-iperf3:latest -s

cat <<"EOT" > /home/ec2-user/run_script.sh
#!/bin/bash

while true; do
    # Call your Python script here
    python3 /home/ec2-user/network_testing.py

    # Sleep for 3 minutes (180 seconds)
    sleep 180
done
EOT

sudo chmod +x /home/ec2-user/run_script.sh
sudo chown ec2-user:ec2-user /home/ec2-user/run_script.sh
sudo /home/ec2-user/run_script.sh &


