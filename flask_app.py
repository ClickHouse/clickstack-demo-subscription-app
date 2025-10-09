from flask import Flask, request, jsonify, send_from_directory, render_template
import clickhouse_connect
import logging
from datetime import datetime
import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from hyperdx.opentelemetry import configure_opentelemetry
from modules.helper_functions import get_parameter_store_value, load_config, setup_hyperdx

# Load environment variables from .env file
load_dotenv(override=True)

app = Flask(__name__, template_folder='templates', static_folder='static')

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Set logger level to ensure HyperDX captures logs properly
logger.setLevel(logging.DEBUG)

# Load configuration
config = load_config(logger = logger)

# ClickHouse configuration
CLICKHOUSE_HOST = config['CLICKHOUSE_HOST']
CLICKHOUSE_PORT = int(config['CLICKHOUSE_PORT'])
CLICKHOUSE_USERNAME = config['CLICKHOUSE_USERNAME']
CLICKHOUSE_PASSWORD = config['CLICKHOUSE_PASSWORD']
CLICKHOUSE_DATABASE = config['CLICKHOUSE_DATABASE']

# HyperDX configuration
HYPERDX_API_KEY = config['HYPERDX_API_KEY']
OTEL_SERVICE_NAME = config['OTEL_SERVICE_NAME']
OTEL_EXPORTER_OTLP_ENDPOINT = config['OTEL_EXPORTER_OTLP_ENDPOINT']
HYPERDX_ENABLE_ADVANCED_NETWORK_CAPTURE = config['HYPERDX_ENABLE_ADVANCED_NETWORK_CAPTURE']
HYPERDX_SERVICE_NAME = config['HYPERDX_SERVICE_NAME']
HYPERDX_ENDPOINT = config['HYPERDX_ENDPOINT']

# Other configurable values
TABLE_NAME = os.getenv('CLICKHOUSE_TABLE_NAME', 'subscriptions')
APP_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
APP_PORT = int(os.getenv('FLASK_PORT', '8000'))
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes', 'on')

# Initialize HyperDX
setup_hyperdx(logger = logger)

def get_clickhouse_client():
    """Get ClickHouse client connection"""
    try:
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            username=CLICKHOUSE_USERNAME,
            password=CLICKHOUSE_PASSWORD,
            database=CLICKHOUSE_DATABASE
        )
        logger.info("Successfully connected to ClickHouse")
        return client
    except Exception as e:
        logger.error(f"Failed to connect to ClickHouse: {e}")
        return None

def init_database():
    """Initialize the database table for subscriptions"""
    client = get_clickhouse_client()
    if not client:
        logger.error("Cannot initialize database - no ClickHouse connection")
        return False

    try:
        # Create table for storing form submissions
        create_table_query = f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id UUID DEFAULT generateUUIDv4(),
            name String,
            company String,
            email String,
            source String,
            submitted_at DateTime DEFAULT now(),
            ip_address String
        ) ENGINE = MergeTree()
        ORDER BY submitted_at
        """

        client.command(create_table_query)
        logger.info(f"Database table '{TABLE_NAME}' initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False
    finally:
        client.close()

@app.route('/')
def index():
    """Serve the main HTML page with injected config"""
    logger.info("Serving main page")
    hyperdx_config = {
        'api_key': HYPERDX_API_KEY,
        'service_name': HYPERDX_SERVICE_NAME,
        'endpoint': HYPERDX_ENDPOINT
    }
    return render_template('index.html', hyperdx_config=hyperdx_config)

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    """Handle form submissions and store in ClickHouse"""
    logger.info("Processing subscription request")
    try:
        # Get JSON data from request
        data = request.get_json()
        #sanatizing 
        logger.debug(f"Received subscription data with fields: {data.keys()}")
        
        # Validate required fields
        required_fields = ['name', 'email', 'source']
        for field in required_fields:
            if not data.get(field):
                logger.warning(f"Missing required field: {field}")
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400

        # Get client IP address
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        logger.debug(f"Client IP: {client_ip}")

        # Connect to ClickHouse
        client = get_clickhouse_client()
        if not client:
            logger.error("Database connection failed during subscription")
            return jsonify({
                'success': False,
                'error': 'Database connection failed'
            }), 500

        # Insert data into ClickHouse
        insert_data = [[
            data.get('name', '').strip(),
            data.get('company', '').strip(),
            data.get('email', '').strip().lower(),
            data.get('source', '').strip(),
            datetime.now(),
            client_ip
        ]]

        client.insert(
            TABLE_NAME,
            insert_data,
            column_names=['name', 'company', 'email', 'source', 'submitted_at', 'ip_address']
        )
        client.close()
        
        logger.info(f"New subscription from ******** via {insert_data[0][3]}")
        
        return jsonify({
            'success': True,
            'message': 'Successfully subscribed to updates!'
        })

    except Exception as e:
        logger.error(f"Error processing subscription: {e}")
        return jsonify({
            'success': False,
            'error': 'An error occurred while processing your subscription'
        }), 500

@app.route('/api/subscribers', methods=['GET'])
def get_subscribers():
    """Get subscriber statistics (optional endpoint for admin)"""
    logger.info("Fetching subscriber statistics")
    try:
        client = get_clickhouse_client()
        if not client:
            logger.error("Database connection failed during stats retrieval")
            return jsonify({'error': 'Database connection failed'}), 500

        # Get basic statistics
        total_subscribers = client.command(f'SELECT COUNT(*) FROM {TABLE_NAME}')
        logger.debug(f"Total subscribers: {total_subscribers}")

        # Get subscribers by source
        source_stats = client.query(
            f'SELECT source, COUNT(*) as count FROM {TABLE_NAME} GROUP BY source ORDER BY count DESC'
        ).result_rows
        logger.debug(f"Source statistics: {source_stats}")

        # Get recent subscribers (last 7 days)
        recent_subscribers = client.command(
            f'SELECT COUNT(*) FROM {TABLE_NAME} WHERE submitted_at >= now() - INTERVAL 7 DAY'
        )
        logger.debug(f"Recent subscribers (7 days): {recent_subscribers}")

        client.close()

        return jsonify({
            'total_subscribers': total_subscribers,
            'recent_subscribers': recent_subscribers,
            'source_breakdown': [{'source': row[0], 'count': row[1]} for row in source_stats]
        })

    except Exception as e:
        logger.error(f"Error getting subscriber stats: {e}")
        return jsonify({'error': 'Failed to retrieve statistics'}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    logger.debug("Health check requested")
    try:
        client = get_clickhouse_client()
        if client:
            # Test database connection
            client.command('SELECT 1')
            client.close()
            logger.info("Health check passed - database connected")
            return jsonify({
                'status': 'healthy',
                'database': 'connected',
                'timestamp': datetime.now().isoformat()
            })
        else:
            logger.error("Health check failed - database disconnected")
            return jsonify({
                'status': 'unhealthy',
                'database': 'disconnected',
                'timestamp': datetime.now().isoformat()
            }), 503
    except Exception as e:
        logger.error(f"Health check failed with error: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503

# Serve static files (CSS, JS, images)
@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory('static/css', filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory('static/js', filename)

@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory('static/images', filename)

if __name__ == '__main__':
    # Initialize database on startup
    if init_database():
        logger.info(f"Starting Flask application on {APP_HOST}:{APP_PORT}...")
        app.run(host=APP_HOST, port=APP_PORT, debug=FLASK_DEBUG)
    else:
        logger.error("Failed to initialize database. Please check your ClickHouse connection.")
