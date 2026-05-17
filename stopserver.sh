#!/bin/bash
PORT=5100
PIDS=$(lsof -ti :$PORT)
if [ -z "$PIDS" ]; then
  echo "Nothing running on port $PORT"
else
  echo "$PIDS" | xargs kill -9
  echo "Killed process(es) on port $PORT: $PIDS"
fi
