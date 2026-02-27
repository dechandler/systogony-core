
import datetime
import json
import logging
import os

import yaml

from declib import DeclibConfig

from .exceptions import NoSuchEnvironmentError, BlueprintLoaderError


class SystogonyConfig(DeclibConfig):
    """

    """
    def __init__(self, name, log, config_args=None):

        #
        extra_defaults = {
            'blueprint_path': "blueprint",
            'secrets_dir': "secrets",
            'tf_env_dir': "terraform",
            'ansible_dir': os.path.abspath(
                os.path.join(os.environ['HOME'], "src/systogony-automation/ansible")
            ),

            'environments': {},
            'default_env': None,
            'env_name': "default",

            'use_cache': False,
            'force_cache_regen': False,

            'ask_become_pass': True,
            'ask_vault_pass': False
        }
        path_opts = [
            'blueprint_path', 'secrets_dir', 'tf_env_dir', 'ansible_dir'
        ]
        super().__init__(
            "systogony",
            log,
            config_args=config_args,
            extra_defaults=extra_defaults,
            path_opts=path_opts
        )


        if self['default_env']:
            self._apply_default_env()

        self['svc_defaults'] = self._get_service_defaults()


    def _apply_default_env(self):

        default_env = self['default_env']
        if default_env not in self['environments']:
            raise NoSuchEnvironmentError(
                f"default_env defined ({default_env}) "
                + "but no matching name under environments"
            )
        self.update(self['environments'][default_env])

    def _get_service_defaults(self):
        """
        Since services can reference other services to inherit from,
        there is no way to know which order to load the files,
        so we're looping over it a few times until they stop resolving.

        """
        self.raw_defaults = {}
        self.defaults = {}

        # Load files into raw_defaults, and set defaults if
        #   the file doesn't reference another service
        self._load_service_default_files()

        # Resolve services iteratively until complete or unchanged
        prev_resolved_len = -1
        while (
            len(self.defaults) < len(self.raw_defaults)
            and len(self.defaults) != prev_resolved_len
        ):
            prev_resolved_len = len(self.defaults)

            for svc_name, svc_vars in self.raw_defaults.items():
                if svc_name not in self.defaults:
                    self._resolve_service(svc_name, svc_vars)

        # Warn if any services didn't resolve to a root service
        if len(self.defaults) < len(self.raw_defaults):
            self.log.warning(f"Unresolved services: {set(self.raw_defaults) - set(self.defaults)}")

        return self.defaults


    def _load_service_default_files(self):
        """

        """
        # Define services.d path
        # TODO: Move this to config file
        defaults_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "services.d"
        )
        self.log.info(f"Svc defaults directory: {defaults_dir}")

        # Walk services.d and compile list of .yaml file paths
        paths = [
            os.path.join(r, f)
            for r, _, files in os.walk(defaults_dir)
            for f in files
            if f.endswith(".yaml")
        ]
        for path in paths:
            # Parse filename for service name
            svc_name, _ = os.path.splitext(os.path.basename(path))
            try:
                # Load defaults file
                with open(path) as fh:
                    svc_vars = yaml.safe_load(fh)
                self.log.debug(f"Loaded svc defaults: {path}")

            except yaml.scanner.ScannerError:
                # Not yaml parseable - drop a warning and ignore
                self.log.warn(f"File with .yaml extension at {path} is not YAML parseable, aborting...")
                continue
            except Exception as e:
                # Catchall - deal with this if it comes up
                self.log.warn(' '.join([
                    "Unexpected exception while loading",
                    f"yaml at {path}: ({e.__class__}) {e}"
                ]))
                continue

            # If a parent service isn't specified, mark as fully loaded
            if svc_vars.get('service') in [svc_name, None]:
                svc_vars['service'] = svc_name
                self.defaults[svc_name] = svc_vars
            self.raw_defaults[svc_name] = svc_vars

        self.log.debug(f"Resolved service defaults: {[*self.defaults.keys()]}")


    def _resolve_service(self, svc_name, svc_vars):

        # Load defaults from parent service
        parent_svc_name = svc_vars['service']
        try:
            parent_vars = {**self.defaults[parent_svc_name]}
        except KeyError:
            # If a parent service is specified,
            #   the referenced service should exist.
            raise MissingServiceError(
                f"Missing from service.d: {parent_svc_name} ({svc_name}.yaml)"
            )

        # Update service vars with parent defaults
        del svc_vars['service']
        parent_vars.update(svc_vars)
        self.defaults[svc_name] = parent_vars

        # Mark complete if resolved
        if parent_vars['service'] == parent_svc_name:
            return parent_svc_name
