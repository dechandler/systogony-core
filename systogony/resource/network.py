
import ipaddress
import json
import logging

from functools import cached_property

from .resource import Resource
from ..exceptions import BlueprintLoaderError


log = logging.getLogger("systogony")


class Network(Resource):



    def __init__(self, env, net_spec, parent_net=None):


        log.info(f"New network: {net_spec['name']} ({net_spec['type']})")
        log.debug(f"    Spec: {json.dumps(net_spec, indent=4)}")

        self.resource_type = "network"
        self.shorthand_type_matches = ["network", "net", "subnet"]
        super().__init__(env, net_spec)

        self.parent_net = parent_net

        self.network_lineage = self.get_net_lineage(self)
        self.network = self.network_lineage[0]

        self.fqn = tuple([
            ("network", net.name) for net in self.network_lineage
        ])

        #self.net = self._resource

        # Register this resource
        # if parent_net:
        #     parent_net.subnets[self.fqn] = self
        if parent_net:
            parent_net.subnets[self.name] = self


        self.interfaces = {}  # registry of Interface by .fqn
        self.networks = {self.fqn: self}  # static (self)
        # self.services  # property via service_instances
        # self.service_instances  # property via host if self in host ifaces

        # Other attributes
        self.claims_default = self.spec.get('default', True)
        self.net_type = self.spec['type']
        self.subnets = {}  # registry of Network
        # self.acls_forward = {}  # registry of Acl
        #self.acls = {'forward': {}}

        self.spec_var_ignores.extend([
            'subnets', 'cidr', 'cidr_prefix_offset', 'cidr_index',
            'type', 'router'
        ])
        # self.extra_vars  # property


        # Lineage for walking up and down the heirarchy
        self.parents = [] if parent_net is None else [parent_net]
        self.children = self.subnets


        # Determine network CIDR
        if 'cidr' in net_spec:
            self.cidr = self.spec['cidr']
        elif not parent_net:
            raise BlueprintLoaderError(f"No CIDR specified and no parent net for {self.name}")
        elif 'cidr_prefix_offset' in net_spec and parent_net.cidr:
            self.cidr = self._get_subnet_cidr(
                parent_net.cidr,
                net_spec['cidr_prefix_offset'],
                net_spec['cidr_index']
            )
        else:
            raise BlueprintLoaderError(f"No cidr or constructor: {self.name}")

        # Generate subnets by scheme determined by net_type
        if self.net_type == "router":
            self.gen_router_subnets()
        if self.net_type == "isolation":
            self.gen_isolation_subnets()

        self.ports = {'any': "*"}

        log.debug(f"Network data: {json.dumps(self.serialized, indent=4)}")


    # @cached_property
    # def extra_vars(self):

    #     return {
    #         'cidr': self.cidr,
    #         'rules': {'forward': self.rules['forward']}
    #     }

    # @property
    # def metahost_name(self):

    #     return f"net_{self.short_fqn_str}_metahost"

    @property
    def introspect(self):

        return {
            'name': self.name,
            'short_fqn': self.short_fqn_str,
            'cidr': self.cidr,
            'net_type': self.net_type,
            #'parent': net.parent,
            'hosts': [host.short_fqn_str for host in self.hosts.values()],
            'interfaces': [iface.short_fqn_str for iface in self.interfaces.values()],
            'subnets': [*self.subnets],
            'vars': self.vars
        }


    @property
    def hosts(self):

        hosts = {}

        # direct hosts
        for host in self.env.host_groups.get(self.name, []):
            hosts[host.fqn] = host

        # include subnets
        for subnet in self.subnets.values():
            for host in subnet.hosts.values():
                hosts[host.fqn] = host

        return hosts


    def gen_isolation_subnets(self):

        network = ipaddress.ip_network(self.cidr)
        isolation_cidrs = list(network.subnets(new_prefix=30))
        for i, host in enumerate(self.hosts.values()):
            subnet_spec = {
                'name': host.name,
                'type': "isolated",
                'cidr': str(isolation_cidrs[i + 1])  # skip first subnet
            }
            Network(self.env, subnet_spec, parent_net=self)
            #self.subnets[host.name].hosts = {host.fqn: host}



    def gen_router_subnets(self):

        for subnet_name, subnet_spec in self.spec.get('subnets', {}).items():
            subnet_spec['name'] = subnet_name
            Network(self.env, subnet_spec, parent_net=self)



    @property
    def services(self):

        return {
            inst.service.fqn: inst.service
            for inst in self.service_instances.values()
        }

    @property
    def service_instances(self):

        # instances = {}
        # for iface in self.interfaces.values():
        #     for inst in iface.host.service_instances.values():
        #         if iface in inst.interfaces

        return {
            inst.fqn: inst
            for inst in iface.host.service_instances.values()
            for iface in self.interfaces.values()
        }

    # @property
    # def interfaces(self):

    #     ifaces = {}
    #     for host in self.hosts.values():
    #         ifaces.update(host.interfaces)
    #     return ifaces

    @property
    def addresses(self):

        return {self.fqn: [self.cidr]}


    def get_net_lineage(self, net):
        if not net.parent_net:
            return [net] 
        return [*self.get_net_lineage(net.parent_net), net]

    def _get_extra_serial_data(self):

        return {
            'network': str(self.network.fqn),
            'cidr': self.cidr,
            'subnets': {
                str(subnet.fqn): subnet.serialized
                for subnet in self.subnets.values()
            }
        }

    def add_host(self, host):

        self.hosts[host.fqn] = host
        if self.parent_net:
            self.parent_net.add_host(host)


    def generate_isolated_networks(self, group_host_names):

        if self.net_type != "isolation":
            return {}

        network = ipaddress.ip_network(self.cidr)
        isolation_cidrs = list(network.subnets(new_prefix=30))

        for i, host_name in enumerate(group_host_names):
            self.subnets[host_name] = Network(
                {
                    'name': host_name,
                    'type': "isolated",
                    'cidr': isolation_cidrs[i + 1]  # skip first subnet
                },
                self.env,
                parent_net=self
            )
            host = self.env.hosts[(('host', host_name),)]
            self.subnets[host_name].add_host(host)

        return self.subnets



    def _get_subnet_cidr(self, parent_cidr, prefix_offset, index):

        return str(
            list(ipaddress.IPv4Network(
                parent_cidr
            ).subnets(
                new_prefix=(int(parent_cidr.split('/')[1]) + prefix_offset)
            ))[index]
        )
