#!/bin/bash
# Monitor and restart NEMO MQTT services if they die
# Usage: ./monitor_services.sh [--daemon]

set -e

# Configuration
REDIS_PORT=6379
MQTT_PORT=1883
CHECK_INTERVAL=10  # seconds
LOG_FILE="/var/log/nemo-mqtt-monitor.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] SUCCESS: $1${NC}" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}" | tee -a "$LOG_FILE"
}

# Check if Redis is running
check_redis() {
    if redis-cli -p "$REDIS_PORT" ping > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Check if Mosquitto is running
check_mosquitto() {
    if nc -z localhost "$MQTT_PORT" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Check if Redis-MQTT Bridge service is running
check_mqtt_service() {
    if pgrep -f "redis_mqtt_bridge" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Start Redis
start_redis() {
    log "Starting Redis..."
    
    if command -v systemctl > /dev/null 2>&1; then
        sudo systemctl start redis-server || sudo systemctl start redis
    elif command -v service > /dev/null 2>&1; then
        sudo service redis-server start || sudo service redis start
    else
        redis-server --daemonize yes
    fi
    
    sleep 2
    
    if check_redis; then
        log_success "Redis started successfully"
        return 0
    else
        log_error "Failed to start Redis"
        return 1
    fi
}

# Start Mosquitto
start_mosquitto() {
    log "Starting Mosquitto..."
    
    if command -v systemctl > /dev/null 2>&1; then
        sudo systemctl start mosquitto
    elif command -v service > /dev/null 2>&1; then
        sudo service mosquitto start
    else
        mosquitto -d
    fi
    
    sleep 2
    
    if check_mosquitto; then
        log_success "Mosquitto started successfully"
        return 0
    else
        log_error "Failed to start Mosquitto"
        return 1
    fi
}

# Start Redis-MQTT Bridge service
start_mqtt_service() {
    log "Starting Redis-MQTT Bridge service..."
    
    if command -v systemctl > /dev/null 2>&1 && systemctl list-unit-files | grep -q nemo-mqtt; then
        sudo systemctl start nemo-mqtt
    else
        # Start as background process
        cd /opt/nemo || cd "$(dirname "$(dirname "$0")")"
        nohup python -m NEMO_mqtt.redis_mqtt_bridge > /dev/null 2>&1 &
    fi
    
    sleep 2
    
    if check_mqtt_service; then
        log_success "MQTT service started successfully"
        return 0
    else
        log_error "Failed to start MQTT service"
        return 1
    fi
}

# Monitor and restart if needed
monitor_services() {
    log "Starting service monitor..."
    
    while true; do
        # Check Redis
        if ! check_redis; then
            log_error "Redis is not running"
            start_redis
        fi
        
        # Check Mosquitto
        if ! check_mosquitto; then
            log_error "Mosquitto is not running"
            start_mosquitto
        fi
        
        # Check MQTT service
        if ! check_mqtt_service; then
            log_error "MQTT service is not running"
            start_mqtt_service
        fi
        
        # Check Redis queue length
        QUEUE_LENGTH=$(redis-cli -n 1 llen nemo_mqtt_events 2>/dev/null || echo "0")
        if [ "$QUEUE_LENGTH" -gt 1000 ]; then
            log_warning "Message queue is large: $QUEUE_LENGTH messages"
        fi
        
        # Sleep before next check
        sleep "$CHECK_INTERVAL"
    done
}

# Check service status
check_status() {
    echo "Checking NEMO MQTT services..."
    echo ""
    
    # Redis
    if check_redis; then
        log_success "Redis: Running"
        QUEUE_LENGTH=$(redis-cli -n 1 llen nemo_mqtt_events 2>/dev/null || echo "0")
        echo "  Queue length: $QUEUE_LENGTH messages"
    else
        log_error "Redis: Not running"
    fi
    
    # Mosquitto
    if check_mosquitto; then
        log_success "Mosquitto: Running"
    else
        log_error "Mosquitto: Not running"
    fi
    
    # Redis-MQTT Bridge service
    if check_mqtt_service; then
        log_success "Redis-MQTT Bridge: Running"
        PID=$(pgrep -f "redis_mqtt_bridge" | head -n 1)
        echo "  PID: $PID"
    else
        log_error "Redis-MQTT Bridge: Not running"
    fi
    
    echo ""
}

# Main
case "${1:-}" in
    --daemon)
        log "Starting in daemon mode..."
        monitor_services
        ;;
    --status)
        check_status
        ;;
    --start)
        log "Starting all services..."
        start_redis
        start_mosquitto
        start_mqtt_service
        check_status
        ;;
    --stop)
        log "Stopping all services..."
        pkill -f "redis_mqtt_bridge" || true
        
        if command -v systemctl > /dev/null 2>&1; then
            sudo systemctl stop mosquitto || true
            sudo systemctl stop redis || true
        fi
        
        log_success "Services stopped"
        ;;
    *)
        echo "Usage: $0 [--daemon|--status|--start|--stop]"
        echo ""
        echo "Options:"
        echo "  --daemon    Run in daemon mode, continuously monitoring services"
        echo "  --status    Check status of all services"
        echo "  --start     Start all services"
        echo "  --stop      Stop all services"
        echo ""
        echo "If no option is provided, runs a single health check."
        check_status
        ;;
esac

