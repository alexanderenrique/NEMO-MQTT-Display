#!/usr/bin/env python3
"""
Simple script to test the MQTT monitor API
"""
import logging
import requests
import json

logger = logging.getLogger(__name__)


def test_api():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    url = "http://127.0.0.1:8000/mqtt/monitor/api/"

    logger.info("Testing MQTT Monitor API...")
    logger.info("URL: %s", url)
    logger.info("-" * 50)

    try:
        # Make the request
        response = requests.get(url)

        logger.info("Status Code: %s", response.status_code)
        logger.info("Headers: %s", dict(response.headers))
        logger.info("Content Type: %s", response.headers.get('content-type', 'Unknown'))
        logger.info("-" * 50)

        # Try to parse as JSON
        try:
            data = response.json()
            logger.info("JSON Response: %s", json.dumps(data, indent=2))
        except json.JSONDecodeError:
            logger.info("Response is not JSON: %s", response.text[:500])

    except requests.exceptions.ConnectionError:
        logger.error("Could not connect to the server")
        logger.error("Make sure Django is running on http://127.0.0.1:8000/")
    except Exception as e:
        logger.error("ERROR: %s", e)

if __name__ == "__main__":
    test_api()
