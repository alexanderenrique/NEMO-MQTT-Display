#!/bin/bash
# Format code with black and isort

echo "Formatting code..."

# Install formatting tools
pip install black isort

# Format with black
echo "Running black..."
black src/NEMO_mqtt/

# Sort imports with isort
echo "Running isort..."
isort src/NEMO_mqtt/

echo "Code formatting complete!"
