"""
Django management command to set up NEMO integration for the MQTT plugin.

Configures NEMO settings and URLs. Use --install-package to also install the
plugin via pip (when developing or installing from source).
"""

import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Set up NEMO integration for the MQTT plugin (configures settings and URLs)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--nemo-path",
            type=str,
            help="Path to NEMO-CE installation (if not in current directory)",
        )
        parser.add_argument(
            "--backup",
            action="store_true",
            help="Create backup files before modifying",
        )
        parser.add_argument(
            "--install-package",
            action="store_true",
            help="Install the plugin via pip first (pip install -e .)",
        )
        parser.add_argument(
            "--gitlab",
            action="store_true",
            help="Production/GitLab mode: do not modify files; print config snippets to add to your version-controlled repo.",
        )
        parser.add_argument(
            "--write-urls",
            action="store_true",
            help="Write MQTT URL include to NEMO/urls.py. If not set, only print instructions (no file changes).",
        )

    def handle(self, *args, **options):
        nemo_path = options.get("nemo_path") or os.getcwd()
        create_backup = options.get("backup", False)
        install_package = options.get("install_package", False)
        gitlab_mode = options.get("gitlab", False)
        write_urls = options.get("write_urls", False)

        self.stdout.write(
            self.style.SUCCESS(
                f"Setting up NEMO MQTT Plugin integration in: {nemo_path}"
            )
        )

        if install_package:
            self._install_package()

        # Check if we're in a NEMO installation (only required when writing urls)
        if not self._is_nemo_installation(nemo_path) and not gitlab_mode and write_urls:
            raise CommandError(f"{nemo_path} does not appear to be a NEMO installation")

        if gitlab_mode:
            self._print_gitlab_instructions()
            return

        # By default only print instructions; write urls only when --write-urls is set
        self._print_integration_instructions()

        success_count = 0
        if write_urls:
            if self._configure_urls(nemo_path, create_backup):
                success_count += 1
            self.stdout.write(
                self.style.SUCCESS(f"\nModified {success_count} file(s).")
            )
        else:
            self.stdout.write(
                self.style.NOTICE("\nNo files were modified. Add the snippets above to your project, or run with --write-urls to add the URL include to NEMO/urls.py.")
            )

        self.stdout.write("\nNext steps:")
        self.stdout.write("1. Add 'NEMO_mqtt' to INSTALLED_APPS in your settings if not already present.")
        self.stdout.write("2. Run migrations: python manage.py migrate nemo_mqtt")
        self.stdout.write("3. Start NEMO: python manage.py runserver")
        self.stdout.write("4. Configure MQTT at /customization/mqtt/")

    def _install_package(self):
        """Install the plugin via pip in editable mode"""
        plugin_dir = Path(__file__).resolve().parent.parent.parent.parent.parent
        self.stdout.write("Installing Python package...")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", str(plugin_dir)],
                check=True,
                capture_output=True,
            )
            self.stdout.write(self.style.SUCCESS("[OK] Package installed"))
        except subprocess.CalledProcessError as e:
            raise CommandError(
                f"pip install failed: {e.stderr.decode() if e.stderr else e}"
            )

    def _print_gitlab_instructions(self):
        """Print config snippets for version-controlled deployment (no file changes)."""
        self.stdout.write(
            self.style.WARNING(
                "\nGitLab/Production mode: no files were modified on this server.\n"
            )
        )
        self.stdout.write(
            "Add the following to your NEMO repo and deploy via GitLab/Ansible.\n"
        )
        self._print_integration_instructions()

        self.stdout.write(self.style.SUCCESS("\nNext steps:"))
        self.stdout.write("  • Commit and push the changes, then deploy to the server.")
        self.stdout.write("  • On the server after deploy: python manage.py migrate nemo_mqtt")
        self.stdout.write("  • Configure MQTT at /customization/mqtt/\n")

    def _print_integration_instructions(self):
        """Print INSTALLED_APPS, LOGGING, and urls.py snippets (no file changes)."""
        self.stdout.write(self.style.SUCCESS("\n1. In settings (e.g. settings.py or settings_prod.py), add to INSTALLED_APPS:"))
        self.stdout.write("""
    'NEMO_mqtt',
""")

        self.stdout.write(self.style.NOTICE("\n2. (Optional) If you use LOGGING in settings, add a 'NEMO_mqtt' logger with your preferred level and handlers (e.g. DEBUG in dev, INFO or WARNING in production)."))

        self.stdout.write(self.style.SUCCESS("\n3. In NEMO/urls.py, add:"))
        self.stdout.write("""
    # MQTT plugin URLs
    path("mqtt/", include("NEMO_mqtt.urls")),
""")
        self.stdout.write("   (inside urlpatterns, or use: urlpatterns += [ path(...), ])\n")

    def _is_nemo_installation(self, path):
        """Check if the path contains a NEMO installation"""
        nemo_path = Path(path)
        return (nemo_path / "manage.py").exists() and (nemo_path / "NEMO").exists()

    def _backup_file(self, file_path):
        """Create a backup of the file"""
        backup_path = f"{file_path}.backup"
        if not os.path.exists(backup_path):
            with open(file_path, "r") as original:
                with open(backup_path, "w") as backup:
                    backup.write(original.read())
            self.stdout.write(f"[OK] Created backup: {backup_path}")
        return backup_path

    def _configure_urls(self, nemo_path, create_backup):
        """Configure NEMO URLs for MQTT plugin"""
        urls_file = Path(nemo_path) / "NEMO" / "urls.py"

        if not urls_file.exists():
            self.stdout.write(f"WARNING: Could not find NEMO/urls.py at {urls_file}")
            return False

        if create_backup:
            self._backup_file(str(urls_file))

        with open(urls_file, "r") as f:
            content = f.read()

        # Check if already added
        if "NEMO_mqtt.urls" in content:
            self.stdout.write(f"[OK] MQTT URLs already added to {urls_file}")
            return True

        # Add MQTT URLs
        mqtt_urls = """
    # Add MQTT plugin URLs
    urlpatterns += [
        path("mqtt/", include("NEMO_mqtt.urls")),
    ]"""

        # Find a good place to add the URLs
        lines = content.split("\n")
        if lines and lines[-1].strip() == "":
            lines = lines[:-1]

        lines.extend(mqtt_urls.split("\n"))
        new_content = "\n".join(lines)

        with open(urls_file, "w") as f:
            f.write(new_content)

        self.stdout.write(f"[OK] Added MQTT URLs to {urls_file}")
        return True
