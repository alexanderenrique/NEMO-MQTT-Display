#!/usr/bin/env python3
"""
MQTT Monitoring Runner
This script provides an easy way to run the MQTT monitoring tools with proper environment setup.
"""

import os
import sys
import subprocess
import argparse
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def find_venv():
    """Find the virtual environment"""
    cwd = Path.cwd()
    possible_paths = [
        cwd / "venv",
        cwd / ".venv",
        Path.home() / ".virtualenvs" / "nemo-ce",
    ]

    for venv_path in possible_paths:
        if venv_path.exists() and (venv_path / "bin" / "python").exists():
            return venv_path

    return None


def get_python_executable():
    """Get the Python executable to use"""
    venv_path = find_venv()
    if venv_path:
        return str(venv_path / "bin" / "python")
    else:
        # Fall back to system Python
        return sys.executable


def run_script(script_name, args=None):
    """Run a monitoring script with proper environment"""
    script_dir = Path(__file__).parent
    script_path = script_dir / script_name

    if not script_path.exists():
        logger.error("Script not found: %s", script_path)
        return False

    python_exe = get_python_executable()

    # Prepare command
    cmd = [python_exe, str(script_path)]
    if args:
        cmd.extend(args)

    logger.info("Running: %s", " ".join(cmd))
    logger.info("=" * 60)

    try:
        result = subprocess.run(cmd, cwd=Path.cwd())
        return result.returncode == 0
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return True
    except Exception as e:
        logger.error("Error running script: %s", e)
        return False


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="MQTT Monitoring Tools")
    parser.add_argument(
        "tool",
        choices=["mqtt", "redis", "test"],
        help="Monitoring tool to run: mqtt (full monitor), redis (redis only), test (test signals)",
    )
    parser.add_argument(
        "--args", nargs="*", help="Additional arguments to pass to the tool"
    )

    args = parser.parse_args()

    logger.info("MQTT Plugin Monitoring Tools")
    logger.info("=" * 40)

    # Check if we're in the right directory
    if not (Path.cwd() / "manage.py").exists():
        logger.error("Please run this script from the NEMO project root directory")
        return 1

    # Find and display Python environment
    venv_path = find_venv()
    if venv_path:
        logger.info("Using virtual environment: %s", venv_path)
    else:
        logger.warning("No virtual environment found, using system Python")

    logger.info("Python executable: %s", get_python_executable())

    # Run the appropriate tool
    if args.tool == "mqtt":
        success = run_script("mqtt_monitor.py", args.args)
    elif args.tool == "redis":
        success = run_script("redis_checker.py", args.args)
    elif args.tool == "test":
        python_exe = get_python_executable()
        cmd = [python_exe, "manage.py", "test_mqtt_api"]
        if args.args:
            cmd.extend(args.args)
        logger.info("Running: %s", " ".join(cmd))
        logger.info("=" * 60)
        try:
            result = subprocess.run(cmd, cwd=Path.cwd())
            success = result.returncode == 0
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
            success = True
        except Exception as e:
            logger.error("Error: %s", e)
            success = False
    else:
        logger.error("Unknown tool: %s", args.tool)
        return 1

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
