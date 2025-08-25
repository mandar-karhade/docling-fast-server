#!/bin/bash

# Start the Uvicorn server in the background
uvicorn src.main:app --host 0.0.0.0 --port 8000 &

# Start the RQ worker in the background
python -m src.worker &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
