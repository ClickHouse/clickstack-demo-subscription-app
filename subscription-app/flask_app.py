from flask import Flask, request, jsonify, send_from_directory, render_template
import psycopg2
import logging
from datetime import datetime
import os
from hyperdx.opentelemetry import configure_opentelemetry
import requests

app = Flask(__name__, template_folder='templates', static_folder='static')

# Configure logging
logging.getLogger('werkzeug').disabled = True
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()      # get log_level as string
log_level = getattr(logging, log_level, 'INFO')         # convert log_level to numeric
logger = logging.getLogger(__name__)
# Set logger level to ensure HyperDX captures logs properly
logger.setLevel(log_level)

logger.debug("Loading configuration variables")
try:
    # PostgreSQL configuration
    POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
    POSTGRES_USERNAME = os.getenv('POSTGRES_USERNAME', 'postgres')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
    POSTGRES_DATABASE = os.getenv('POSTGRES_DATABASE', 'postgres')

    # HyperDX configuration
    HYPERDX_API_KEY = os.getenv('HYPERDX_API_KEY', '')
    OTEL_SERVICE_NAME = os.getenv('OTEL_SERVICE_NAME', 'subscription-backend')
    OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4318')
    HYPERDX_ENABLE_ADVANCED_NETWORK_CAPTURE = int(os.getenv('HYPERDX_ENABLE_ADVANCED_NETWORK_CAPTURE', '1'))
    HYPERDX_SERVICE_NAME = os.getenv('HYPERDX_SERVICE_NAME', 'subscription-frontend')
    HYPERDX_ENDPOINT = os.getenv('HYPERDX_ENDPOINT', 'http://localhost:4318')

    # Other configurable values
    APP_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
    APP_PORT = int(os.getenv('FLASK_PORT', '8000'))
    FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() in ('true', '1', 'yes', 'on')
    DOCS_LOADER_HOST = os.getenv('DOCS_LOADER_HOST', 'localhost')
    DOCS_LOADER_PORT = int(os.getenv('DOCS_LOADER_PORT', '8001'))
except Exception as e:
    logger.error(f"Failed to load configuration variables: {e}")

def get_psql_connection():
    """Get PostgreSQL client connection"""
    logger.debug("Connecting to PostgreSQL")
    try:
        conn = psycopg2.connect(
            database=POSTGRES_DATABASE,
            user=POSTGRES_USERNAME,
            password=POSTGRES_PASSWORD,
            host=POSTGRES_HOST,
            port=POSTGRES_PORT
        )
        logger.debug("Successfully connected to PostgreSQL")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        return None

def log_request():
    """Log request using standard format"""
    timestamp = datetime.now()
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    user_agent = request.headers.get('User-Agent')
    method = request.method
    path = request.path
    http_version = request.environ.get('SERVER_PROTOCOL')
    logger.info(f'{client_ip} [{timestamp}] "{method} {path} {http_version}" "{user_agent}"')

@app.route('/')
def index():
    """Serve the main HTML page with injected config"""
    logger.debug("Serving main page")
    log_request()
    hyperdx_config = {
        'api_key': HYPERDX_API_KEY,
        'service_name': HYPERDX_SERVICE_NAME,
        'endpoint': HYPERDX_ENDPOINT
    }
    return render_template('index.html', hyperdx_config=hyperdx_config)

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    """Handle form submissions and store in Postgres"""
    logger.debug("Processing subscription request")
    log_request()
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

        logger.debug("Connecting to PostgreSQL")
        conn = get_psql_connection()
        if not conn:
            logger.error("Database connection failed during subscription")
            return jsonify({
                'success': False,
                'error': 'Database connection failed'
            }), 500

        cursor = conn.cursor()

        insert_data = (
            data.get('name', '').strip(),
            data.get('company', '').strip(),
            data.get('email', '').strip().lower(),
            data.get('source', '').strip(),
            datetime.now()
        )

        insert_query = """
            INSERT INTO users (name, company, email, source, submitted_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE SET
                name = EXCLUDED.name,
                company = EXCLUDED.company,
                source = EXCLUDED.source,
                submitted_at = EXCLUDED.submitted_at;
        """

        logger.debug("Inserting data")
        cursor.execute(insert_query, insert_data)

        conn.commit()
        cursor.close()
        conn.close()

        logger.debug(f"New subscription from ******** via {insert_data[0][3]}")

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

@app.route('/load-docs')
def load_docs():
    """Load docs endpoint"""
    docs_loader_endpoint = f"http://{DOCS_LOADER_HOST}:{DOCS_LOADER_PORT}/load"
    logger.debug("Simulate loading docs")
    log_request()
    try:
        response = requests.get(docs_loader_endpoint)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health_check():
    """Health check endpoint"""
    logger.debug("Health check requested")
    log_request()
    try:
        conn = get_psql_connection()
        if conn:
            # Test database connection
            cursor = conn.cursor()
            cursor.execute('SELECT 1;')
            cursor.close()
            conn.close()
            logger.debug("Health check passed - database connected")
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
    log_request()
    return send_from_directory('static/css', filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    log_request()
    return send_from_directory('static/js', filename)

@app.route('/images/<path:filename>')
def serve_images(filename):
    log_request()
    return send_from_directory('static/images', filename)

if __name__ == '__main__':
    logger.info(f"Starting Flask application on {APP_HOST}:{APP_PORT}...")
    app.run(host=APP_HOST, port=APP_PORT, debug=FLASK_DEBUG)
