from flask import Blueprint, Response, stream_with_context, session
from utils import login_required
import time
import json

stream_bp = Blueprint('stream', __name__)

@stream_bp.route('/api/stream')
@login_required
def sse_stream():
    user_id = session.get('user_id')
    
    def event_generator():
        # In a real app, this would hook into Redis PubSub or Kafka
        # to listen for real transaction events.
        # For this demonstration, we yield a ping every 2 seconds
        # and close after 10 seconds to respect Vercel's Serverless limits.
        
        start_time = time.time()
        yield f"data: {json.dumps({'status': 'connected', 'message': 'SSE Real-time connection established'})}\n\n"
        
        while time.time() - start_time < 9:
            time.sleep(2)
            yield f"data: {json.dumps({'status': 'ping', 'timestamp': time.time()})}\n\n"
            
        yield f"data: {json.dumps({'status': 'closed', 'message': 'Connection closed to respect serverless limit'})}\n\n"

    return Response(stream_with_context(event_generator()), mimetype='text/event-stream')
