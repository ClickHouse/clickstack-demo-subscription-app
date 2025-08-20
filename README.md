# hyperdx_demo

This is a front end application that can send telemetry to HyperDX collector.

## How to deploy

1. Deploy HyperDX All-in-One
2. Deploy the front-end application

### Local

Life is easy on local mode, not much to configure

1. I recommend using Docker to deploy all-in-one with a single line command `docker run -p 8080:8080 -p 4317:4317 -p 4318:4318 --name hyperdx docker.hyperdx.io/hyperdx/hyperdx-all-in-one:2.2.1`
2. Go to http://localhost:8080 and configure HyperDX
3. Get the API-Key from the team settings
4. Add the API-Key on index.html in L167
5. Do `pip install -r requirements.txt` (I recommend using venv)
6. Do `python3 flask_app.py`
7. Go to http://localhost:8000
8. Have fun

### Remote (AWS ec2)

1. Create EC2 instance and make sure it has access to internet, and doors 8080, 8000 and 4318 are open to the world wide web
2. Get your ec2 dns name, or a proper dns name if you have one
3. SSH into the ec2 and `docker run -p 8080:8080 -p 4317:4317 -p 4318:4318 -e FRONTEND_URL={{EC2_DNS}}:8080 -e NEXT_PUBLIC_OTEL_EXPORTER_OTLP_ENDPOINT={{EC2_DNS}}:4318 --name hyperdx docker.hyperdx.io/hyperdx/hyperdx-all-in-one:2.2.1` replacing the ECS_DNS with whatever it is
4. Go to http://{{EC2_DNS}}:8080 and configure HyperDX
5. Get the API-Key from the team settings
6. Add the API-Key on index.html in L167
7. Do `pip install -r requirements.txt`
8. Do `python3 flask_app.py`
9. Go to http://{{EC2_DNS}}:8000
10. Have fun

## TODO
- Configure ClickHouse Cloud (instead of local)
- Actually create a deploy pattern, with enviroment variables and stuff