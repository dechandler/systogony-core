"""


"""
import json
import logging
import os
import yaml

from collections import defaultdict

from ..resource import Host, Network, Service


from ..exceptions import (
    BlueprintLoaderError,
    # NonMatchingPathSignal,
    # MissingServiceError,
    NotReadySignal
)

#log = logging.getLogger("systogony")

class Blueprint:

    def __init__(self, env):

        self.env = env
        self.config = env.config
        self.log = self.config.log

        self.svc_defaults = env.config['svc_defaults']
        #del env.config['svc_defaults']

        self.blueprint = self.load_blueprint(self.config['blueprint_path'])

        self.host_groups = defaultdict(list)  # populated by .get_hosts()

    def __getitem__(self, key):
        return self.blueprint[key]



    def _generate_resource(self, ResourceClass, name, spec, **kwargs):

        spec = {} if spec is None else spec
        spec['name'] = name
        return ResourceClass(self.env, spec, **kwargs)

    def populate_env_hosts(self):

        host_groups = defaultdict(list)

        for host_name, host_spec in self.blueprint['hosts'].items():
            host = self._generate_resource(Host, host_name, host_spec)
            for group_name in host.groups:
                host_groups[group_name].append(host)

        self.env.host_groups = {
            group_name: sorted(host_list)
            for group_name, host_list in host_groups.items()
        }

    def populate_env_networks(self):

        # Generate WAN pseudo-network
        self._generate_resource(
            Network, 'wan', {'type': "wan", 'cidr': "0.0.0.0/0"}
        )

        # Create top level network objects (which create their subnets)
        for net_name, net_spec in self.blueprint['networks'].items():
            self._generate_resource(Network, net_name, net_spec)

    def populate_env_interfaces(self):
        """
        Creates Interface objects to connect a network and host

        """
        for host in self.env.hosts.values():
            host.populate_interfaces()

    def populate_env_services(self):

        for net_name, net_spec in self.blueprint['services'].items():
            self._generate_resource(
                Service, net_name, net_spec, svc_defaults=self.svc_defaults
            )

    def populate_env_service_instances(self):
        """
        Creates ServiceInstance objects to connect a service
        and host.

        Since some services may reference other services for
        the hosts it's meant to run on, loop over the services
        until everything is resolved, or it reaches max
        iterations. This is to avoid reference loops, where
        resolution can't be completed.

        """
        i = 0
        max_iterations = 10
        prev_populated_services_len = -1

        populated_services = []
        while (
            len(populated_services) < len(self.env.services)
            and len(populated_services) != prev_populated_services_len
            and i < max_iterations
        ):
            i = i + 1
            prev_populated_services_len = len(populated_services)

            for svc in self.env.services.values():
                if svc.hosts_complete:
                    continue
                try:
                    svc.populate_hosts()
                except NotReadySignal:
                    continue
                populated_services.append(svc.name)

    def populate_env_acls(self):

        # Generate acls
        for resource in self.env.resources.values():
            resource.gen_acls()


    def load_blueprint(self, bp_dir):

        blueprint = {
            'hosts': {},
            'networks': {},
            'services': {}, 
            'vars': {}
        }
        # Load and consolidate blueprint data from files and subdirs
        bp_dir = os.path.expanduser(bp_dir)
        self.log.info(f"Loading blueprint data from {bp_dir}")
        for component, spec in blueprint.items():

            # Generate list of file paths for current blueprint component
            paths = []
            main_file = os.path.join(bp_dir, f"{component}.yaml")
            if os.path.isfile(main_file):
                paths.append(main_file)
            bp_subdir = os.path.join(bp_dir, component)
            if os.path.isdir(bp_subdir):
                for fname in sorted(os.listdir(bp_subdir)):
                    if fname.endswith(".yaml"):
                        paths.append(os.path.join(bp_subdir, fname))

            # Load data from discovered files
            for path in paths:

                try:
                    with open(path) as fh:
                        data = yaml.safe_load(fh) or {}
                except Exception as e: #(
                #         KeyError, TypeError, UnicodeDecodeError,
                #         yaml.scanner.ScannerError, yaml.parser.ParserError
                # ):
                    self.log.warning(f"YAML parse failure, ignoring: {path}")
                    continue

                self.log.debug(f"{component} data loaded from {path}:")
                self.log.debug(json.dumps(data, indent=4))

                # Update component data, but update
                # top-level dictionaries, rather
                # than overwriting
                for conf_key, conf_data in data.items():
                    if type(spec.get(conf_key)) is type(conf_data) is dict:
                        spec[conf_key].update(conf_data)
                    else:
                        spec[conf_key] = conf_data

        return blueprint
