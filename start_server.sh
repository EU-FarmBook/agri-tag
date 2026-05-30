#!/bin/bash
# Start the Agri-Tag API server

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Agri-Tag API...${NC}"

# Check if virtual environment exists
if [ -d ".venv" ]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source venv/bin/activate
else
    echo -e "${RED}Warning: No virtual environment found. Using system Python.${NC}"
fi

# Check if uvicorn is installed
if ! command -v uvicorn &> /dev/null; then
    echo -e "${RED}Error: uvicorn is not installed. Install with: pip install uvicorn${NC}"
    exit 1
fi

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo -e "${YELLOW}Loading environment from .env${NC}"
    export $(grep -v '^#' .env | xargs)
fi

# Default configuration
HOST=${HOST:-"0.0.0.0"}
PORT=${PORT:-"8000"}
WORKERS=${WORKERS:-"1"}

echo -e "${GREEN}Configuration:${NC}"
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Workers: $WORKERS"
echo "  LLM Configured: $([ -n "$DOCINT_LLM_BASE_URL" ] && echo 'Yes' || echo 'No (heuristics only)')"
echo ""

# Start server
echo -e "${GREEN}Starting Uvicorn server...${NC}"
echo -e "${YELLOW}API documentation available at: http://localhost:$PORT/docs${NC}"
echo ""

if [ "$WORKERS" -gt 1 ]; then
    uvicorn app:app --host $HOST --port $PORT --workers $WORKERS
else
    # Use reload in development mode (single worker)
    uvicorn app:app --host $HOST --port $PORT --reload
fi
