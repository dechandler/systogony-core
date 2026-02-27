"""


"""
import logging

from .resource import Resource

log = logging.getLogger("systogony")


class ServiceInstance(Resource):



    def __init__(self, env, service, host, inst_spec):

        log.debug(f"New ServiceInstance: {host.name}.{service.name}")
        log.debug(f"    Service FQN: {service.fqn}")
        log.debug(f"    Host FQN:    {host.fqn}")

        self.resource_type = "service_instance"
        self.shorthand_type_matches = [
            "service-instance", "service_instance", "instance",
            "svc_inst", "svc-inst","inst",
            "service", "svc"
        ]

        if not inst_spec:
            inst_spec = {}
        inst_spec['name'] = service.name
        super().__init__(env, inst_spec)

        self.service = service
        self.host = host
        overrides = { k: v for k, v in (inst_spec or {}).items() }
        self.port_overrides = overrides.get('ports', False)

        self.fqn = tuple([*host.fqn, *service.fqn])



        # Associated resources by type
        self.hosts = {self.host.fqn: self.host}  # static
        self.interfaces = {**host.interfaces}

        log.debug(overrides)



        if 'interfaces' in overrides:
            self.interfaces = self._get_spec_interfaces(
                overrides['interfaces']
            )
        elif 'interfaces' in service.spec:
            self.interfaces = self._get_spec_interfaces(
                service.spec['interfaces']
            )

        log.debug(f"Service Interfaces: {self.interfaces}")

        #self.networks = 
        self.services = {self.service.fqn: self.service}  # static
        self.service_instances = {self.fqn: self}  # static (self)


        # Register this resource
        service.service_instances[host.fqn] = self
        host.service_instances[service.fqn] = self
        for iface in self.interfaces.values():
            iface.service_instances[self.fqn] = self


        # Lineage for walking up and down the heirarchy
        self.parents = [*self.interfaces.values(), host, service]


        # Other attributes
        self.spec_var_ignores.extend(['mounts', 'interfaces', 'ports'])
        self.spec.update(service.vars)
        self.spec.update(overrides)
        # self.extra_vars.update(service.vars)
        # self.extra_vars.update(overrides)
        # self.extra_vars = {}  # default


        # Override service default ports
        # self.ports = { name: num for name, num in service.ports.items() }
        # if 'ports' in overrides:
        #     self.ports.update(overrides['ports'])
        #     #del overrides['ports']

        # 


        # self.extra_vars
        # self.vars = { k: v for k, v in (service.vars).items() }
        # self.vars.update(overrides)


        #log.debug(f"    Data: {json.dumps(self.serialized, indent=4)}")

    @property
    def introspect(self):

        return {
            'name': self.name,
            'short_fqn': self.short_fqn_str,
            'service': self.service.short_fqn_str,
            'host': self.host.short_fqn_str,
            'interfaces': [iface.short_fqn_str for iface in self.interfaces.values()],
            'networks': [net.short_fqn_str for net in self.networks.values()],
            'vars': self.vars
        }


    @property
    def extra_vars(self):

        extra_vars = {}
        extra_vars.update({
            'ports': self.ports,
            'interfaces': [ iface.network.network.name for iface in self.interfaces.values() ]
            #     iface.network.name
            #     for iface in self.interfaces.values()
            # ]
        })
        #extra_vars.update(self.)

        return extra_vars

    @property
    def ports(self):

        if self.port_overrides in [None, {}, []]:
            return {}
        elif self.port_overrides == False:
            return { name: num for name, num in self.service.ports.items() }
        elif type(self.port_overrides) == dict:
            return self.port_overrides
        elif type(self.port_overrides) == list:
            return {
                name: num for name, num
                in self.service.ports.items()
                if name in self.port_overrides
            }

    @property
    def networks(self):

        return {
            iface.network.network.fqn: iface.network.network
            for iface in self.interfaces.values()
        }


    @property
    def ifaces_by_net_fqn(self):
        return {
            iface.network.network.fqn: iface
            for iface in self.host.interfaces.values()
        }


    def _get_extra_serial_data(self):

        return {
            'service': str(self.service.fqn),
            'host': str(self.host.fqn),
            'interfaces': str(self.interfaces),
            'ports': self.ports
        }


    def _get_spec_interfaces(self, ifaces_spec):
        interfaces = {}
        if not ifaces_spec:
            return interfaces


        for shorthand in ifaces_spec:
            matches = self.env.get_shorthand_matches(shorthand)
            for match in matches:
                for match_net in match.networks.values():
                    if match_net.fqn not in self.ifaces_by_net_fqn:
                        continue
                    iface = self.ifaces_by_net_fqn[match_net.fqn]
                    interfaces[iface.fqn] = iface

        return interfaces
