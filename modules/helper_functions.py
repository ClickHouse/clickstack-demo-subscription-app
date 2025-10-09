#!/usr/bin/env python3
import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from hyperdx.opentelemetry import configure_opentelemetry


def get_parameter_store_value(parameter_name, logger, region = None, default_value=None):
    """Get parameter value from AWS Parameter Store"""
    try:
        if region:
            ssm_client = boto3.client('ssm', region_name = region)
        else:
            ssm_client = boto3.client('ssm')
        response = ssm_client.get_parameter(
            Name=parameter_name,
            WithDecryption=True  # Use this for SecureString parameters
        )
        return response['Parameter']['Value']
    except ClientError as e:
        logger.warning(f"Failed to get parameter {parameter_name} from Parameter Store: {e}")
        if default_value is not None:
            logger.info(f"Using default value for {parameter_name}")
            return default_value
        raise e
    except Exception as e:
        logger.error(f"Unexpected error getting parameter {parameter_name}: {e}")
        if default_value is not None:
            return default_value
        raise e

def load_config(logger, region = None):
    """Load configuration from AWS Parameter Store or environment variables"""
    config = {}
    
    # Get parameter store prefix from environment variable
    param_prefix = os.getenv('PARAMETER_STORE_PREFIX', '/caio-hyperdx-demo/frontend')
    
    # Define parameter mappings (Parameter Store suffix -> config key -> default value)
    parameters = {
        # ClickHouse configuration
        '/clickhouse/host': ('CLICKHOUSE_HOST', 'localhost'),
        '/clickhouse/port': ('CLICKHOUSE_PORT', '8123'),
        '/clickhouse/username': ('CLICKHOUSE_USERNAME', 'default'),
        '/clickhouse/password': ('CLICKHOUSE_PASSWORD', ''),
        '/clickhouse/database': ('CLICKHOUSE_DATABASE', 'default'),
        
        # HyperDX configuration
        '/hyperdx/api_key': ('HYPERDX_API_KEY', ''),
        '/hyperdx/service_name': ('HYPERDX_SERVICE_NAME', 'flask-subscription-app'),
        '/hyperdx/endpoint': ('HYPERDX_ENDPOINT', 'https://in-otel.hyperdx.io')
    }
    
    for param_suffix, (env_key, default_value) in parameters.items():
        try:
            # First try Parameter Store
            param_name = f"{param_prefix}{param_suffix}"
            value = get_parameter_store_value(param_name, logger = logger, region = region)
            config[env_key] = value
            logger.info(f"Loaded {env_key} from Parameter Store")
        except:
            # Fallback to environment variable
            env_value = os.getenv(env_key, default_value)
            config[env_key] = env_value
            logger.info(f"Using environment variable for {env_key}")
    return config

def setup_hyperdx(logger):
    """Configure HyperDX OpenTelemetry instrumentation"""
    config = load_config(logger)
    try:
        # Set environment variables for OpenTelemetry
        os.environ['HYPERDX_API_KEY'] = config['HYPERDX_API_KEY']
        os.environ['OTEL_SERVICE_NAME'] = 'my-backend-app'
        os.environ['OTEL_EXPORTER_OTLP_ENDPOINT'] = config['HYPERDX_ENDPOINT']
        
        # Enable advanced network capture if desired
        os.environ['HYPERDX_ENABLE_ADVANCED_NETWORK_CAPTURE'] = '1'        
        
        # Configure HyperDX OpenTelemetry
        configure_opentelemetry()
        
        logger.info("HyperDX OpenTelemetry configured successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to configure HyperDX: {e}")
        return False