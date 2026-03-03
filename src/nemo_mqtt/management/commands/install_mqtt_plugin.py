#!/usr/bin/env python3
"""
Django management command to install the MQTT plugin.

This is a convenience wrapper that runs setup_nemo_integration with --install-package.
For pip-installed deployments, use: setup_nemo_integration
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Install the MQTT plugin (pip install + configure NEMO). Use setup_nemo_integration for config-only."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Force reinstall")
        parser.add_argument(
            "--backup", action="store_true", help="Create backup before modifying"
        )
        parser.add_argument(
            "--gitlab",
            action="store_true",
            help="Production/GitLab mode: do not modify config files; print snippets for your repo.",
        )
        parser.add_argument(
            "--write-urls",
            action="store_true",
            help="Write MQTT URL include to NEMO/urls.py (see setup_nemo_integration --write-urls).",
        )

    def handle(self, *args, **options):
        call_command(
            "setup_nemo_integration",
            install_package=True,
            backup=options["backup"],
            gitlab=options["gitlab"],
            write_urls=options["write_urls"],
        )
