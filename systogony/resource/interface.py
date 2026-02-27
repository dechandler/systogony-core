"""


"""
import ipaddress
import json
import logging

from .resource import Resource


log = logging.getLogger("systogony")


class Interface(Resource):





    def __init__(self, env, iface_spec, network, host):

        log.debug("New Interface")
        log.debug(f"    Network: {network.fqn}")
        log.debug(f"    Host:    {host.fqn}")

        self.resource_type = "interface"
        self.shorthand_type_matches = [
            "interface", "iface",
            "host-interface", "host_interface", "host-iface", "host_iface",
            "net-interface", "net_interface", "net-iface", "net_iface" 
        ]

        super().__init__(env, iface_spec)

        self.fqn = tuple([*network.fqn, *host.fqn])

        self.network = network
        self.host = host
        if self.network.net_type == "isolated":
            net_cidr = ipaddress.ip_network(self.network.cidr)
            self.spec['ip'] = [*net_cidr.hosts()][1]

        # Register this resource


        log.debug(f"Registering to {self.host.name}: {network.network.fqn[0][1]}")
        host.interfaces[network.network.fqn[0][1]] = self
        network.interfaces[host.fqn] = self

        # Associated resources by type
        self.hosts = {self.host.fqn: self.host}  # static
        self.interfaces = {self.fqn: self}  # static
        self.networks = {self.network.fqn: self.network}  # static
        # self.services  # property via service_instances if self in host interfaces
        # self.service_instances   # property via host if self in host ifaces

        # Lineage for walking up and down the heirarchy
        self.parents = [network, host]

        # Other attributes
        # self.acls_ingress = {}
        # self.acls_egress = {}
        # self.acls = {'ingress': self.acls_ingress, 'egress': self.acls_egress}

        self.spec_var_ignores.extend(['groups', 'network'])
        # self.extra_vars = {}  # default

        #network = self.spec['network']
        #print(network, host.fqn)

        self.ports = {'any': "*"}


        log.debug(f"    Interface data: {json.dumps(self.serialized, indent=4)}")


    @property
    def introspect(self):

        return {
            'name': self.name,
            'short_fqn': self.short_fqn_str,
            'network': self.network.short_fqn_str,
            'host': self.host.short_fqn_str,
            # 'ingress': self.short_fqns_strs(self.acls['ingress']),
            # 'egress': self.short_fqns_strs(self.acls['egress']),
            'vars': self.vars
        }

    def _get_xgress_ips(self, rule_type, remotes, network):

        ips = []
        for target in remotes.values():
            for net_fqn, addrs in target.addresses.items():
                log.debug(f"addrs: {target.name} {net_fqn} {addrs}")
                if net_fqn == self.network.network.fqn:
                    ips.extend(addrs)

        log.debug(f"IPs for {self.name}: {ips}")
        return ips





    @property
    def firewall_rules(self):

        rules = {
            'ingress': {},
            'egress': {},
            'forward': {}
        }
        get_rule = lambda acl: {
            'ports': acl.ports,
            'name': acl.name,
            'description': acl.description
        }

        # Ingress rules (INPUT)
        for acl in self.acls['ingress'].values():
            rule = get_rule(acl)
            rule['source_addrs'] = list(set(self._get_xgress_ips(
                'ingress', acl.sources, self.network.network
            )))
            rules['ingress'][acl.fqn] = rule

        # Egress rules (OUTPUT)
        for acl in self.acls['egress'].values():
            rule = get_rule(acl)
            rule['destination_addrs'] = list(set(self._get_xgress_ips(
                'egress', acl.sources, self.network.network
            )))
            rules['egress'][acl.fqn] = rule

        # Return rules if no router service
        for inst in self.service_instances.values():
            if inst.service.name == "router":
                break
        else:
            log.debug(rules)
            return {self.network.network.fqn: rules}

        # Forward rules (FORWARD)
        forward_acls = self.network.network.acls['forward']
        for acl in forward_acls.values():
            rule = {
                'name': acl.name,
                'description': acl.description,
                'ports': acl.ports,
                'source_addrs': [],
                'destination_addrs': []
            }

            net_fqn = self.network.network.fqn

            for src in acl.sources.values():
                rule['source_addrs'].extend(src.addresses.get(net_fqn, []))
            for dest in acl.destinations.values():
                rule['destination_addrs'].extend(dest.addresses.get(net_fqn, []))

            # Dedupe
            rule['source_addrs'] = list(set(rule['source_addrs']))
            rule['destination_addrs'] = list(set(rule['destination_addrs']))

            rules['forward'][acl.fqn] = rule

        log.debug(rules)
        return {self.network.network.fqn: rules}


    @property
    def services(self):

        return {
            inst.service.fqn: inst.service
            for inst in self.service_instances.values()
        }

    @property
    def service_instances(self):

        return {
            inst.fqn: inst
            for inst in self.host.service_instances.values()
            if self.fqn in [*inst.interfaces]
        }

    @property
    def addresses(self):

        if 'ip' not in self.spec:
            log.debug(f"Addresses requested, ip missing from spec, spec is {self.spec}")
            return {self.network.network.fqn: []}

        log.debug(f"{self.network.network.fqn}: {[str(self.spec['ip'])]}")
        return {self.network.network.fqn: [str(self.spec['ip'])]}

    @property
    def extra_vars(self):

        fw_rules = {}

        for rule_type, typed_rules in self.firewall_rules[self.network.network.fqn].items():
            fw_rules[rule_type] = []
            log.debug(typed_rules)
            for rule in typed_rules.values():
                # log.debug("STUFF")
                # log.debug(rule)
                fw_rules[rule_type].append(rule)

        extra_vars = {}
        if 'ip' in self.spec:
            extra_vars['ip'] = f"{self.spec['ip']}"
        if 'domain' in self.network.network.spec:
            extra_vars['fqdn'] = f"{self.host.name}.{self.network.network.spec['domain']}"
        extra_vars.update({
            'net_name': self.network.network.name,
            'default': self.is_default_iface,
            'firewall_rules': fw_rules
        })
        return extra_vars

    def _get_extra_serial_data(self):

        data = {}
        if 'ip' in self.spec:
            data['ip'] = f"{self.spec['ip']}"

        return data
