from flask import Flask, request, jsonify, send_from_directory, render_template_string
import clickhouse_connect
import logging
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, static_folder='static')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ClickHouse configuration
CLICKHOUSE_HOST = os.getenv('CLICKHOUSE_HOST', 'localhost')
CLICKHOUSE_PORT = int(os.getenv('CLICKHOUSE_PORT', 8123))
CLICKHOUSE_USERNAME = os.getenv('CLICKHOUSE_USERNAME', 'default')
CLICKHOUSE_PASSWORD = os.getenv('CLICKHOUSE_PASSWORD', '')
CLICKHOUSE_DATABASE = os.getenv('CLICKHOUSE_DATABASE', 'default')

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
        create_table_query = """
        CREATE TABLE IF NOT EXISTS subscriptions (
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
        logger.info("Database table 'subscriptions' initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False
    finally:
        client.close()

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('static', 'index.html')

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    """Handle form submissions and store in ClickHouse"""
    try:
        # Get JSON data from request
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'email', 'source']
        for field in required_fields:
            if not data.get(field):
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                }), 400
        
        # Get client IP address
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        
        # Connect to ClickHouse
        client = get_clickhouse_client()
        if not client:
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
            'subscriptions', 
            insert_data,
            column_names=['name', 'company', 'email', 'source', 'submitted_at', 'ip_address']
        )
        client.close()
        
        logger.info(f"New subscription from {insert_data[0][0]} via {insert_data[0][3]}")
        
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
    try:
        client = get_clickhouse_client()
        if not client:
            return jsonify({'error': 'Database connection failed'}), 500
        
        # Get basic statistics
        total_subscribers = client.command('SELECT COUNT(*) FROM subscriptions')
        
        # Get subscribers by source
        source_stats = client.query(
            'SELECT source, COUNT(*) as count FROM subscriptions GROUP BY source ORDER BY count DESC'
        ).result_rows
        
        # Get recent subscribers (last 7 days)
        recent_subscribers = client.command(
            'SELECT COUNT(*) FROM subscriptions WHERE submitted_at >= now() - INTERVAL 7 DAY'
        )
        
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
    try:
        client = get_clickhouse_client()
        if client:
            # Test database connection
            client.command('SELECT 1')
            client.close()
            return jsonify({
                'status': 'healthy',
                'database': 'connected',
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'status': 'unhealthy',
                'database': 'disconnected',
                'timestamp': datetime.now().isoformat()
            }), 503
    except Exception as e:
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
        logger.info("Starting Flask application...")
        app.run(host='0.0.0.0', port=8000, debug=True)
    else:
        logger.error("Failed to initialize database. Please check your ClickHouse connection.")
