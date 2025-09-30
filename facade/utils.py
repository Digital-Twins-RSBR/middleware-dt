# --- HTTP session helper for gateway requests (moved out of models for reuse) ---
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- Small helpers to format InfluxDB line protocol safely ---
def _escape_tag(v):
    s = str(v)
    return s.replace('\\', '\\\\').replace(' ', '\\ ').replace(',', '\\,').replace('=', '\\=')


def _format_field_value(v):
    try:
        from decimal import Decimal
    except Exception:
        Decimal = None
    # Allow explicit 'raw' integer-suffixed strings (e.g. '0i') to pass through
    # (keeps backwards compatibility for intentionally crafted literals)
    if isinstance(v, str) and v.endswith('i'):
        core = v[:-1]
        if core.lstrip('-').isdigit():
            return v
    # Normalize booleans and integers to floats to avoid Influx field-type conflicts
    if isinstance(v, bool):
        return str(1.0 if v else 0.0)
    if isinstance(v, int):
        return str(float(v))
    if Decimal and isinstance(v, Decimal):
        return str(float(v))
    try:
        if isinstance(v, float):
            return str(v)
    except Exception:
        pass
    esc = str(v).replace('"', '\\"')
    return f'"{esc}"'


def format_influx_line(measurement, tags: dict, fields: dict, timestamp=None):
    mt = str(measurement).replace(' ', '\\ ').replace(',', '\\,')
    tag_parts = []
    for k, val in (tags or {}).items():
        tag_parts.append(f"{k}={_escape_tag(val)}")
    field_parts = []
    for k, val in (fields or {}).items():
        field_parts.append(f"{k}={_format_field_value(val)}")
    if tag_parts:
        left = f"{mt},{','.join(tag_parts)}"
    else:
        left = mt
    right = ','.join(field_parts)
    if timestamp is not None:
        return f"{left} {right} {timestamp}"
    return f"{left} {right}"

# URLLC Redis-based Session Manager - Global singleton across all processes
class URLLCRedisSessionManager:
    """Redis-backed HTTP Session Manager for true global singleton across processes"""
    
    def __init__(self):
        self._redis_client = None
        self._local_sessions = {}  # In-memory cache for sessions
        self._lock = None
        self._setup_redis()
    
    def _setup_redis(self):
        """Setup Redis connection with optimized local Redis"""
        try:
            import redis
            import threading
            self._lock = threading.Lock()
            
            # Use local Redis (installed in same container) for optimal performance
            redis_host = os.getenv('REDIS_HOST', '127.0.0.1')
            redis_port = int(os.getenv('REDIS_PORT', 6379))
            
            self._redis_client = redis.Redis(
                host=redis_host, 
                port=redis_port, 
                decode_responses=True,
                socket_connect_timeout=0.1,  # Ultra-fast connection timeout
                socket_timeout=0.5,          # Fast operation timeout
                health_check_interval=10     # Health check every 10s
            )
            
            # Test connection
            self._redis_client.ping()
            print(f"[URLLC-RedisSessionManager] ✅ Connected to local Redis at {redis_host}:{redis_port}")
            
        except Exception as e:
            print(f"[URLLC-RedisSessionManager] ⚠️ Redis unavailable ({e}), using local singleton fallback")
            self._redis_client = None
            import threading
            self._lock = threading.Lock()
    
    def _get_session_key(self, gateway_id: int):
        """Generate Redis key for gateway session tracking"""
        return f"urllc:session:{gateway_id}:active"
    
    def get_session(self, gateway_id: int):
        """Get or create a true global singleton session for the gateway using Redis coordination"""
        
        with self._lock:
            # Check if we already have this session locally
            if gateway_id in self._local_sessions:
                return self._local_sessions[gateway_id]
            
            # Use Redis for global coordination
            session_key = self._get_session_key(gateway_id)
            connection_count_key = f"urllc:session:{gateway_id}:connections"
            
            if self._redis_client:
                try:
                    # Atomic increment of connection count
                    connection_count = self._redis_client.incr(connection_count_key)
                    self._redis_client.expire(connection_count_key, 3600)  # 1 hour TTL
                    
                    if connection_count == 1:
                        # We're the first process to use this gateway
                        self._redis_client.setex(session_key, 3600, "primary")
                        print(f"[URLLC-RedisSessionManager] 🎯 PRIMARY session for gateway {gateway_id} (connections: {connection_count})")
                    else:
                        # Other processes are already using this gateway
                        print(f"[URLLC-RedisSessionManager] 🔗 SHARED session for gateway {gateway_id} (connections: {connection_count})")
                    
                except Exception as e:
                    print(f"[URLLC-RedisSessionManager] Redis coordination error: {e}, proceeding with local session")
            
            # Create ultra-optimized session with extreme connection limiting
            session = requests.Session()
            
            # URLLC-specific configuration with extreme connection limiting
            retries = Retry(
                total=1,                    # Only 1 retry for speed
                backoff_factor=0.01,       # 10ms backoff
                status_forcelist=(502, 503, 504),
                allowed_methods=frozenset(['GET', 'POST'])
            )
            
            # Ultra-aggressive single connection policy with Redis coordination
            adapter = HTTPAdapter(
                max_retries=retries,
                pool_connections=1,        # Single connection per gateway PER PROCESS
                pool_maxsize=1,           # Maximum 1 connection in pool
                pool_block=True           # Block and reuse existing connection
            )
            
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            
            # Ultra-low timeout and persistent connection headers
            session.timeout = 0.05  # 50ms default timeout - ultra aggressive!
            session.headers.update({
                'Connection': 'keep-alive',
                'Keep-Alive': 'timeout=10, max=1000',  # Long-lived connection
                'User-Agent': f'URLLC-Client-Gateway{gateway_id}'  # Unique identifier
            })
            
            self._local_sessions[gateway_id] = session
            print(f"[URLLC-RedisSessionManager] ⚡ Created local session for gateway {gateway_id}")
            
            return session
    
    def close_session(self, gateway_id: int):
        """Close session and clean up Redis coordination state"""
        with self._lock:
            # Close local session
            if gateway_id in self._local_sessions:
                try:
                    self._local_sessions[gateway_id].close()
                    del self._local_sessions[gateway_id]
                    print(f"[URLLC-RedisSessionManager] ✅ Closed local session for gateway {gateway_id}")
                except Exception as e:
                    print(f"[URLLC-RedisSessionManager] ⚠️ Error closing session: {e}")
            
            # Decrement Redis connection count
            if self._redis_client:
                try:
                    connection_count_key = f"urllc:session:{gateway_id}:connections"
                    remaining = self._redis_client.decr(connection_count_key)
                    
                    if remaining <= 0:
                        # Last process using this gateway, cleanup completely
                        session_key = self._get_session_key(gateway_id)
                        self._redis_client.delete(session_key, connection_count_key)
                        print(f"[URLLC-RedisSessionManager] 🧹 Last connection - cleaned all Redis state for gateway {gateway_id}")
                    else:
                        print(f"[URLLC-RedisSessionManager] 📉 Decremented connections for gateway {gateway_id}, remaining: {remaining}")
                        
                except Exception as e:
                    print(f"[URLLC-RedisSessionManager] Redis cleanup error: {e}")
    
    def close_all_sessions(self):
        """Close all sessions and clean up Redis state"""
        with self._lock:
            # Close all local sessions
            for gateway_id in list(self._local_sessions.keys()):
                self.close_session(gateway_id)
            
            # Clean up all Redis session keys
            if self._redis_client:
                try:
                    keys = self._redis_client.keys("urllc:session:*:active")
                    if keys:
                        self._redis_client.delete(*keys)
                        print(f"[URLLC-RedisSessionManager] Cleaned {len(keys)} Redis session keys")
                except Exception as e:
                    print(f"[URLLC-RedisSessionManager] Redis cleanup error: {e}")
            
            print(f"[URLLC-RedisSessionManager] Closed all sessions")

# URLLC Singleton Session Manager - Ultra-efficient HTTP connection management
class URLLCSessionManager:
    """Singleton HTTP Session Manager optimized for Ultra-Reliable Low Latency Communication"""
    
    _instance = None
    _sessions = {}
    _lock = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(URLLCSessionManager, cls).__new__(cls)
            import threading
            cls._lock = threading.Lock()
        return cls._instance
    
    def get_session(self, gateway_id: int):
        """Get or create a singleton session for the gateway with URLLC optimizations"""
        
        with self._lock:
            if gateway_id not in self._sessions:
                # Create ultra-optimized session for URLLC
                session = requests.Session()
                
                # URLLC-specific retry policy: fast fail for low latency
                retries = Retry(
                    total=1,                    # Only 1 retry for speed
                    backoff_factor=0.01,       # 10ms backoff
                    status_forcelist=(502, 503, 504),
                    allowed_methods=frozenset(['GET', 'POST'])
                )
                
                # Ultra-lightweight adapter for minimal overhead  
                # Force single connection with aggressive connection reuse
                adapter = HTTPAdapter(
                    max_retries=retries,
                    pool_connections=1,        # Single connection per gateway
                    pool_maxsize=1,           # Maximum 1 connection in pool
                    pool_block=True           # Block and reuse existing connection
                )
                
                session.mount('http://', adapter)
                session.mount('https://', adapter)
                
                # Set ultra-aggressive default timeout and connection reuse
                session.timeout = 0.1  # 100ms default timeout
                
                # Force persistent connection headers
                session.headers.update({
                    'Connection': 'keep-alive',
                    'Keep-Alive': 'timeout=1, max=1000'
                })
                
                self._sessions[gateway_id] = session
                print(f"[URLLC-SessionManager] Created singleton session for gateway {gateway_id}")
            
            return self._sessions[gateway_id]
    
    def close_session(self, gateway_id: int):
        """Close and remove session for specific gateway"""
        with self._lock:
            if gateway_id in self._sessions:
                try:
                    self._sessions[gateway_id].close()
                    print(f"[URLLC-SessionManager] Closed session for gateway {gateway_id}")
                except Exception as e:
                    print(f"[URLLC-SessionManager] Error closing session for gateway {gateway_id}: {e}")
                finally:
                    del self._sessions[gateway_id]
    
    def close_all_sessions(self):
        """Close all sessions - useful for cleanup"""
        with self._lock:
            for gateway_id in list(self._sessions.keys()):
                self.close_session(gateway_id)
            print(f"[URLLC-SessionManager] Closed all sessions")

# Global session manager instances - Serial request processing for true connection control
_redis_session_manager = URLLCRedisSessionManager()
_local_session_manager = URLLCSessionManager()

# Global request lock to serialize all HTTP requests (prevents connection multiplication)
import threading
_request_lock = threading.Lock()

def get_session_for_gateway(gateway_id: int):
    """Get singleton session for gateway - Redis-backed with local fallback and serialized access"""
    with _request_lock:  # Serialize all session access
        try:
            return _redis_session_manager.get_session(gateway_id)
        except Exception as e:
            print(f"[SessionManager] Redis fallback to local: {e}")
            return _local_session_manager.get_session(gateway_id)

def close_gateway_session(gateway_id: int):
    """Close specific gateway session in both Redis and local managers"""
    with _request_lock:
        try:
            _redis_session_manager.close_session(gateway_id)
        except Exception:
            pass
        try:
            _local_session_manager.close_session(gateway_id)
        except Exception:
            pass

def close_all_sessions():
    """Close all HTTP sessions - Redis and local cleanup"""
    with _request_lock:
        try:
            _redis_session_manager.close_all_sessions()
        except Exception as e:
            print(f"[SessionManager] Redis cleanup error: {e}")
        try:
            _local_session_manager.close_all_sessions()
        except Exception as e:
            print(f"[SessionManager] Local cleanup error: {e}")
