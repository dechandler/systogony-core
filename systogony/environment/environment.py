
import json
import logging
import os

from functools import cached_property

import yaml

from .blueprint import Blueprint

from ..resource import Acl

from ..exceptions import (
    BlueprintLoaderError,
    # NonMatchingPathSignal,
    # MissingServiceError,
    # NotReadySignal
)


log = logging.getLogger("systogony")


class Environment:

    def __init__(self, config):

        self.config = config
        self.log = config.log

        #self.query = ResourceShorthandQuery(self)

        (
            self.names,
            self.hosts, self.host_groups,
            self.networks, self.interfaces,
            self.services, self.service_instances,
            self.acls,
        ) = {}, {}, {}, {}, {}, {}, {}, {}

        self.blueprint = Blueprint(self)
        self.blueprint.populate_env_hosts()
        self.blueprint.populate_env_networks()
        self.blueprint.populate_env_interfaces()
        self.blueprint.populate_env_services()
        self.blueprint.populate_env_service_instances()
        self.blueprint.populate_env_acls()

        self.vars = self.blueprint['vars']



    @property
    def resources(self):

        return {
            **self.networks,
            **self.hosts,
            **self.interfaces,
            **self.services,
            **self.service_instances,
            **self.acls
        }

    @property
    def introspect(self):

        return {
            'networks': [ r.introspect for r in self.networks.values() ],
            'hosts': [ r.introspect for r in self.hosts.values() ],
            'interfaces': [ r.introspect for r in self.interfaces.values() ],
            'services': [ r.introspect for r in self.services.values() ],
            'service_instances': [ r.introspect for r in self.service_instances.values() ],
            'acls': [ r.introspect for r in self.acls.values() ],
        }

    def register(self, resource):

        if resource.name not in self.names:
            self.names[resource.name] = []
        self.names[resource.name].append(resource)
        #self.resources[resource.fqn] = resource
        registries = {
            'host': self.hosts,
            'interface': self.interfaces,
            'network': self.networks,
            'service': self.services,
            'service_instance': self.service_instances,
            'acl': self.acls
        }
        registries[resource.resource_type][resource.fqn] = resource


    def get_shorthand_matches(self, shorthand_str):

        self.log.debug(f"Shorthand Lookup: {shorthand_str}")

        # Split shorthand on . to 
        shorthand = shorthand_str.split('.')

        # The last segment of the shorthand must explicitly
        #   match the name of the resource, so get
        #   each resource with that name
        name = shorthand[-1]

        rtypes = ['service', 'service_instance', 'host', 'network', 'interface']

        matches = { k: [] for k in rtypes }
        for resource in self.names.get(name, []):
            if resource.is_shorthand_match(shorthand):
                self.log.debug(f"Possible match: '{shorthand_str}' to {resource.name}")
                matches[resource.resource_type].append(resource)

        # Iterate resource type priorities and return a single resource
        for rtype in rtypes:
            if matches[rtype]:
                return matches[rtype]

        # Error if no matches for shorthand
        raise BlueprintLoaderError(f"No resource matching {shorthand_str}")

    def gen_acl(self, origin, acl_spec, sources, destinations):
        """


        Called from Resource._gen_acls_by_spec_type

        """
        Acl(self, origin, acl_spec, sources, destinations)
