#!/bin/bash
# Wrapper script for MCP server - logs environment for debugging

LOG_FILE="/tmp/mcp_wrapper.log"
echo "=== MCP Server Wrapper Started at $(date) ===" > "$LOG_FILE"
echo "PWD: $(pwd)" >> "$LOG_FILE"
echo "Arguments: $@" >> "$LOG_FILE"
echo "Environment:" >> "$LOG_FILE"
env | sort >> "$LOG_FILE"
echo "=== Starting server ===" >> "$LOG_FILE"

# Execute the actual server, capturing output
exec "$@" 2>> "$LOG_FILE"
