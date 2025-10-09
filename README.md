# ClickHouse Subscription App

A Flask-based web application that showcases ClickHouse features while collecting user subscriptions. The app is fully instrumented with HyperDX OpenTelemetry for observability and monitoring.

## Overview

This project demonstrates:
- **ClickHouse Integration**: Stores subscription data in a ClickHouse database
- **HyperDX Observability**: Full OpenTelemetry instrumentation for monitoring and debugging, both in front-end (browser) and back-end (Python)

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Browser   │───▶│   Flask App      │───▶│   ClickHouse    │
│                 │    │  (Port 8000)     │    │   Database      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │ OTel data
                                ▼
                       ┌──────────────────┐    ┌─────────────────┐
                       │     HyperDX      │───▶│   ClickHouse    │
                       │  (Observability) │    │   Database      │
                       └──────────────────┘    └─────────────────┘
```

## Prerequisites

- Docker and Docker Compose
- AWS CLI configured (for Parameter Store access)
- ClickHouse database instance
- HyperDX OTEL collector (recommended to deploy [HyperDX All in one](https://clickhouse.com/docs/use-cases/observability/clickstack/deployment/all-in-one))

## Quick Start

Set all configurations before deploying

1. **Clone and Configure**
   ```bash
   git clone <your-repo>
   cd clickhouse-subscription-app
   ```

   Change the file `docker-compose.yml` with your settings. Alternativaly, create a .env file with your configurations (recommended for local mode only)

2. **Deploy**
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

3. **Access Application**
   - Local: http://localhost:8000
   - Cloud: http://YOUR_PUBLIC_IP:8000

## Configuration

### Required Parameters

Configure these parameters before deployment:

#### 1. AWS Configuration (optional: if using Parameter Store)
```bash
# In docker-compose.yml or .env
AWS_DEFAULT_REGION=us-west-2  # Change to your AWS region
```

#### 2. Parameter Store Prefix (optional: if using Parameter Store)
```bash
PARAMETER_STORE_PREFIX=/caio-hyperdx-demo/frontend  # Change to your prefix
```

#### 3. ClickHouse Database Settings

This will be used to create an API route to store form submitted data into Clickhouse. These don't need to be the same used for HyperDX later on.

`username` must have CREATE permissions on `database`

**Option A: Use AWS Parameter Store (Recommended for AWS Deployment)**
```bash
# Set these parameters in AWS Parameter Store:
/your-prefix/clickhouse/host        # ClickHouse server hostname
/your-prefix/clickhouse/port        # Usually 8443 for ClickHouse Cloud
/your-prefix/clickhouse/username    # Database username
/your-prefix/clickhouse/password    # Database password
/your-prefix/clickhouse/database    # Database name
```

**Option B: Use Environment Variables (Recommended for local deployment only)**
```bash
# In docker-compose.yml or .env (.env will override anything you set in docker-compose.yml)
CLICKHOUSE_HOST=your-clickhouse-host
CLICKHOUSE_PORT=8123
CLICKHOUSE_USERNAME=default
CLICKHOUSE_PASSWORD=your-password
CLICKHOUSE_DATABASE=your-database
```

#### 4. HyperDX Observability Settings

These will be used to send telemetry to HyperDX. Instructions to setup HyperDX can be found in [HyperDX Collector setup with ClickHouse Cloud](#hyperdx-collector-setup-with-clickhouse-cloud)

**Option A: Use AWS Parameter Store (Recommended)**
```bash
# Set these parameters in AWS Parameter Store:
/your-prefix/hyperdx/api_key       # Your HyperDX API key
/your-prefix/hyperdx/service_name  # Service identifier for HyperDX
/your-prefix/hyperdx/endpoint      # Usually https://in-otel.hyperdx.io
```

**Option B: Use Environment Variables**
```bash
# In docker-compose.yml or .env
HYPERDX_API_KEY=your-hyperdx-api-key
HYPERDX_SERVICE_NAME=my-subscription-app
HYPERDX_ENDPOINT=https://in-otel.hyperdx.io
```

### Optional Configuration

```bash
# Application settings
FLASK_PORT=8000                    # Change if port 8000 is occupied. Remember to change ports: in docker-compose.yml as well
FLASK_DEBUG=false                  # Set to true for development
LOG_LEVEL=INFO                     # DEBUG, INFO, WARNING, ERROR

# Database table name
CLICKHOUSE_TABLE_NAME=subscriptions  # Customize table name
```

## HyperDX Collector setup with ClickHouse Cloud
Setting up HyperDX Collector is required for this demo. Deploying the entire HyperDX setup is optional, but it is simpler

```bash
docker run -p 8080:8080 -p 4317:4317 -p 4318:4318 \
    -e FRONTEND_URL={YOUR_INSTANCE_IP_OR_URL}:8080 \
    -e CLICKHOUSE_ENDPOINT=instance.us-west-2.aws.clickhouse.cloud:8443 \
    -e CLICKHOUSE_USER=default \
    -e CLICKHOUSE_PASSWORD=password \
    -e HYPERDX_OTEL_EXPORTER_CLICKHOUSE_DATABASE=hyperdx \
    --name hyperdx \
    docker.hyperdx.io/hyperdx/hyperdx-all-in-one:2.2.1
```
This setup will use a Clickhouse instance you provide. The CLICKHOUSE_USER must have CREATE permission in HYPERDX_OTEL_EXPORTER_CLICKHOUSE_DATABASE.

After deployment, go to {YOUR_INSTANCE_IP_OR_URL}:8080 and setup HyperDX for the first time, and grab the API key under Team Settings.

The HYPERDX_ENDPOINT will be {YOUR_INSTANCE_IP_OR_URL}:4318.

To use HyperDX UI, you can either use this deployment as well, or configure [ClickStack Cloud](https://clickhouse.com/docs/use-cases/observability/clickstack/deployment/hyperdx-clickhouse-cloud) (recommended). 

Eventually ClickStack will also have the OTEL Collector, and this step will be irrelevant (just grab API key from ClickStack).

## AWS Parameter Store Setup

Refer to [AWS documentation](https://docs.aws.amazon.com/systems-manager/latest/userguide/sysman-paramstore-su-create.html) to create the parameters in Parameter Store.

We recommend creating an [instance profile](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_use_switch-role-ec2_instance-profiles.html) with permissions to your parameters, and using it on the EC2 you will use to host this app.

## Deployment Options

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

#run app
python flask_app.py
```

### Docker Deployment
```bash
./deploy.sh
```

### Cloud Deployment (AWS EC2 Example)
```bash
# 1. Launch EC2 instance with appropriate IAM role
# 2. Install Docker
sudo yum update -y
sudo yum install docker -y
sudo systemctl start docker
sudo usermod -a -G docker ec2-user #or ubuntu, depending on which image you're using

# 3. Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 4. Deploy your app
git clone <your-repo>
cd clickhouse-subscription-app
./deploy.sh
```

### Instrumenting EC2

To instrument EC2 to collect metrics (e.g. CPU, RAM), you need to change the `ec2_config.yaml` file, to put your hyperdx collector endpoint, API key, and change your service name (optional).

To actually instrument there are 2 options.

#### Instrumenting EC2 directly
```bash
./instrument_ec2.sh
```

#### Instrumenting EC2 via deploy.sh
```bash
./deploy.sh --instrument_ec2
```

By adding `--instrument_ec2` flag, the deployment will include the EC2 instrumentation

## Project Structure

```
clickhouse-subscription-app/
├── deploy.sh                # Deployment script
├── docker-compose.yml       # Docker configuration
├── Dockerfile               # Container build instructions
├── ec2_config.yaml          # Config for EC2 Otel Collector for metrics (optional)
├── flask_app.py             # Main Flask application
├── requirements.txt         # Python dependencies
├── instrument_ec2.sh        # Script to instrument EC2 metrics (optional)
├── .env                     # Environment variables (create this)
├── templates/
│   └── index.html           # Main web page template
├── modules/
│   └── __init__.py          # Blank init
│   └── helper_functions.py  # Centralizing functions not related to flask
├── static/
│   └── css/
│       └── clickhouse_css.css
└── logs/                 # Application logs (auto-created)
```

## Troubleshooting

### Common Issues

**1. Database Connection Failed**
```bash
# Check ClickHouse connectivity
docker exec flask-subscription-app python -c "
import clickhouse_connect
client = clickhouse_connect.get_client(host='YOUR_HOST')
print('Connected successfully!')
"
```

**2. Parameter Store Access Denied**
- Ensure your AWS credentials have `ssm:GetParameter` permissions
- Check that parameter names match your `PARAMETER_STORE_PREFIX`

**3. HyperDX Not Receiving Data**
- Verify your `HYPERDX_API_KEY` is correct
- Check network connectivity to `HYPERDX_ENDPOINT`
- Review browser console for JavaScript errors

**4. Port Already in Use**
```bash
# Change port in docker-compose.yml
ports:
  - "8001:8000"  # Use port 8001 instead
```

**5. Cheching if EC2 collector is working**
```bash
sudo journalctl -u otelcol-contrib -f
```

Running this will give you more insights whether data is being sent, or if there are any error logs.

**6. Application maintenance**

This is meant to be a mock application. If you plan to host it for long periods of time, pay attention to disk usage, especially system logs

### Viewing Logs
```bash
# Application logs
docker compose logs -f flask-app

# ClickHouse query logs (if enabled)
tail -f logs/app.log
```

Application logs will be sent to HyperDX, therefore if the setup was successful, you can track from there.

### Health Checks
```bash
# Quick health check
curl http://localhost:8000/health

# Subscriber statistics
curl http://localhost:8000/api/subscribers
```

### Making Changes
- Frontend: Edit `templates/index.html` and `static/css/`
- Backend: Modify `flask_app.py`
- Configuration: Update `docker-compose.yml` or `.env`

## Security Considerations

- **Never commit secrets**: Use Parameter Store or environment variables
- **Network Security**: Restrict ClickHouse access to your application
- **Input Validation**: All form inputs are validated and sanitized
- **Container Security**: Application runs as non-root user

## Performance Notes

- **ClickHouse**: Optimized for analytical workloads, excellent for time-series data
- **Flask**: Suitable for moderate traffic; consider Gunicorn for production
- **Docker**: Resource limits can be configured in docker-compose.yml

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Support

- **ClickHouse Documentation**: https://clickhouse.com/docs
- **HyperDX Documentation**: https://docs.hyperdx.io
- **Flask Documentation**: https://flask.palletsprojects.com