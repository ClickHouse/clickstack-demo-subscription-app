sudo apt-get update
sudo apt-get -y install wget
wget https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.81.0/otelcol-contrib_0.81.0_linux_arm64.deb
sudo dpkg -i otelcol-contrib_0.81.0_linux_arm64.deb
rm otelcol-contrib_0.81.0_linux_arm64.deb
sudo chmod 755 /etc/otelcol-contrib/config.yaml
sudo cp ./config/otel-collector/ec2_config.yaml /etc/otelcol-contrib/config.yaml
export OTEL_SERVICE_NAME='my-backend-app'
sudo systemctl restart otelcol-contrib
