
import json
import logging

from collections import defaultdict, OrderedDict
from functools import cached_property

from .resource import Resource
from .service_instance import ServiceInstance

from ..exceptions import BlueprintLoaderError, MissingServiceError, NotReadySignal

log = logging.getLogger("systogony")


class Service(Resource):



    def __init__(self, env, svc_spec, svc_defaults):

        self.svc_defaults = svc_defaults  # env.config['svc_defaults']

        log.info(f"New Service: {svc_spec['name']}")
        log.debug(f"    Spec: {json.dumps(svc_spec)}")

        self.resource_type = "service"
        self.shorthand_type_matches = ["service", "svc"]

        super().__init__(env, svc_spec)

        self.hosts_complete = False


        # Associated resources by type
        # self.networks = 
        self.services = {self.fqn: self}  # static (self)
        self.service_instances = {}  # registry of ServiceInstance by fqn

        # Lineage for walking up and down the heirarchy
        self.parent = None
        self.children = self.service_instances


        # Other attributes
        self.port_overrides = self.spec.get('ports', False)
        #self.ports = self.spec.get('ports', {})

        #self.spec_var_ignores.extend(['ports'])
        # self.extra_vars = {}  # default


        self.parents = []

        log.debug(f"Service data: {json.dumps(self.serialized, indent=4)}")

    @property
    def introspect(self):

        return {
            'name': self.name,
            'short_fqn': self.short_fqn_str,
            'service_instances': self.short_fqns_strs(self.service_instances),
            'vars': self.vars

        }


    @property
    def ports(self):

        if self.port_overrides in [None, {}, []]:
            return {}
        if type(self.port_overrides) == dict:
            return self.port_overrides

        ports = {
            name: num for name, num
            in (self.var_inheritance.get('ports') or {}).items()
        }

        if self.port_overrides == False:
            return { name: num for name, num in ports.items() }

        if type(self.port_overrides) == list:
            return {
                name: num for name, num
                in ports.items()
                if name in self.port_overrides
            }



    @property
    def hosts(self):

        return {
            inst.host.fqn: inst.host
            for inst in self.service_instances.values()
        }

    @property
    def networks(self):

        return {
            iface.network.network.fqn: iface.network.network
            for iface in self.interfaces.values()
        }

    @property
    def interfaces(self):


        ifaces = {}
        for inst in self.service_instances.values():
            ifaces.update(inst.interfaces)
        return ifaces


    def _get_extra_serial_data(self):

        return {
            'service_instances': [
                str(fqn)
                for fqn in self.service_instances
                #for inst in inst_list
            ]


            #self._fqn_str_list(self.service_instances),
            #'allows': self.allows
        }

    @property
    def var_inheritance(self):

        parent = self.spec.get('service')
        log.debug(f"{self.name} inherits from {parent}")

        if not parent:
            self.spec['service'] = self.name
            if self.name in self.svc_defaults:
                inherited = self.svc_defaults[self.name]
            else:
                inherited = {}

        elif parent in self.svc_defaults:
            self.spec['service'] = parent
            inherited = self.svc_defaults[parent]

        elif parent in self.env.blueprint['services']:
            if parent == self.name:
                inherited = {}
            else:
                inherited = self.env.services[('service', parent)].vars
        else:
            raise MissingServiceError("")

        log.debug(f"{self.name} inherits from {parent}: {inherited}")

        return {
            k: v for k, v
            in inherited.items()
        }

    @property
    def vars(self):

        log.debug("SERVICE VARS")
        rvars = {
            k: v for k, v
            in self.var_inheritance.items()
        }
        log.debug(f"  Inheriting: {rvars}")
        rvars.update(self.spec)

        return {
            k: v for k, v in rvars.items()
            if k not in self.spec_var_ignores
        }



    def handle_access(self):


        for shorthand, overrides in self.spec.get('access', {}).items():

            matches = self.env.get_shorthand_matches(shorthand)

            for match in matches:
                for host in match.hosts.values():
                    for inst in self.service_instances.values():
                        host.allows[inst.host.fqn] = {
                            'host': inst.host, 'overrides': overrides
                        }


    def populate_hosts(self):

        log.debug(' '.join([
            f"Attempting to populate hosts for {self.name}:",
            '.'.join([ '.'.join(pair) for pair in self.fqn ])
        ]))

        # All shorthands have resolved previously, so skip
        if self.hosts_complete:
            return

        # Generate list of hosts but return if any shorthands have no matches
        for shorthand, overrides in self.spec.get('hosts', {}).items():
            try:
                matches = self.env.get_shorthand_matches(shorthand)
            except BlueprintLoaderError:
                log.error(f"BlueprintLoaderError for {self.name}: {shorthand}")
                raise BlueprintLoaderError(f'No match for shorthand "{shorthand}" under service hosts {self.name}')

            for match in matches:
                if not match.hosts:
                    log.debug(f"Failed to resolve hosts for {self.name}: {shorthand}")
                    raise NotReadySignal(f"No hosts for {shorthand}")

            host_names = []
            for match in matches:
                for host in match.hosts.values():
                    host_names.append(host.name)
                    ServiceInstance(self.env, self, host, overrides)

            self.log.info(f"Hosts running {self.name}: {', '.join(host_names)}")

        # Mark all host shorthands resolved
        self.hosts_complete = True
