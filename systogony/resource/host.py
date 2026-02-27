"""

"""
import json
import logging

from functools import cached_property

from .resource import Resource
from .interface import Interface

from ..exceptions import BlueprintLoaderError


log = logging.getLogger("systogony")


class Host(Resource):

    def __init__(self, env, host_spec):

        log.debug(f"New Host - spec: {json.dumps(host_spec)}")

        self.resource_type = "host"
        self.shorthand_type_matches = [
            "host", "machine", "system", "server", "device", "dev"
        ]
        super().__init__(env, host_spec)

        # Associated resources by type
        self.hosts = {self.fqn: self}
        self.interfaces = {}  # registrar
        # self.networks  # property - interfaces -> network
        # self.services  # property - service_instances -> services
        self.service_instances = {}  # registrar


        # Lineage for walking up and down the heirarchy
        #self.children = {k: v for k, v in self.interfaces.items()}

        # Other attributes
        self.groups = host_spec.get('groups', [])
        if "os" in host_spec:
            self.groups.append(host_spec['os'])
        if "device" in host_spec:
            self.groups.append(host_spec['device'])

        self.spec_var_ignores.extend(['groups'])
        # self.extra_vars = {}  # default

        self.ports = {'any': "*"}

        log.debug(f"Host data: {json.dumps(self.serialized, indent=4)}")

    @property
    def introspect(self):

        return {
            'name': self.name,
            'short_fqn': self.short_fqn_str,
            'default_iface': self.default_iface.short_fqn_str,
            'interfaces': [iface.short_fqn_str for iface in self.interfaces.values()],
            'networks': [net.short_fqn_str for net in self.networks.values()],
            'services': [svc.short_fqn_str for svc in self.services.values()],
            'svc_instances': [inst.short_fqn_str for inst in self.service_instances.values()],
            'vars': self.vars
        }

    @property
    def default_iface(self):

        # Record claims to being default interface
        # Prioritize claims on host, then which network,
        default_claims = {'hosts': [], 'net': []}
        for iface in self.interfaces.values():
            if 'default' in iface.spec:
                default_claims['hosts'].append(iface)
            if iface.network.claims_default or len(self.interfaces) == 1:
                default_claims['net'].append(iface)

        # Evaluate equally-prioritized claims to default interface
        # Error if ambiguous
        def select_claim(claims):
            if not claims:
                return None

            if len(claims) == 1:
                return claims[0]

            if len(claims > 1):
                raise BlueprintLoaderError(' '.join([
                    "Ambiguous default interface for",
                    f"{self.name}: {claims}"
                ]))

        # Prioritize claims to default interface
        default = (
            select_claim(default_claims['hosts'])
            or select_claim(default_claims['net'])
        )
        if not default:
            raise BlueprintLoaderError(
                f"Unknown default interface for {self.name}"
            )

        for iface in self.interfaces.values():
            iface.is_default_iface = True if iface == default else False
        
        return default


    @property
    def networks(self):



        return {
            iface.network.fqn: iface.network
            for iface in self.interfaces.values()
        }

    @property
    def services(self):

        return {
            inst.service.fqn: inst.service
            for inst in self.service_instances.values()
        }


    @cached_property
    def mounts(self):

        mounts = []
        mounts.extend(self.spec.get('mounts', []))
        for inst in self.service_instances.values():
            mounts.extend(inst.spec.get('mounts', []))

        return mounts

    @property
    def firewall_rules(self):

        rules = {}
        for iface in self.interfaces.values():
            rules.update(iface.firewall_rules)
        log.debug("Firewall Rules")
        log.debug(rules)
        return rules


    @property
    def extra_vars(self):

        # rules = {}
        # for net_fqn, net_rules in self.firewall_rules.items():
        #     net_name = self.env.networks[net_fqn].name
        #     rules[net_name] = {}
        #     for rule_type, typed_rules in net_rules.items():
        #         rules[net_name][rule_type] = []
        #         for acl_fqn, rule in typed_rules.items():
        #             log.debug(rule)
        #             rules[net_name][rule_type].append(rule)

            #     rules[str(net_fqn)][rule_type]



        extra_vars = {
            'service_instances': {
                inst.name: inst.vars
                for inst in self.service_instances.values()
            },
            'network_interfaces': {
                net_name: iface.vars
                for net_name, iface in self.interfaces.items()
            },
            'mounts': self.mounts,
            #'rules': rules
        }



        return extra_vars


    def populate_interfaces(self):

        log.debug(f"Iface Specs for {self.name}: {self.spec.get('interfaces', {})}")

        # Create and register interfaces
        for iface_net_name, iface_spec in self.spec.get('interfaces', {}).items():
            log.debug(f"Iface Net Name: {iface_net_name}")
            log.debug(f"Iface Spec: {json.dumps(iface_spec)}")
            self._add_interface(iface_net_name, iface_spec=iface_spec)

        # Record claims to being default interface
        default_claims = {'hosts': [], 'net': []}
        for iface in self.interfaces.values():
            if 'default' in iface.spec:
                default_claims['hosts'].append(iface)
            if iface.network.claims_default:
                default_claims['net'].append(iface)

        # Evaluate equally-prioritized claims to default interface
        # Error if ambiguous
        def select_claim(claims):
            if not claims:
                return None

            if len(claims) == 1:
                return claims[0]

            if len(claims > 1):
                raise BlueprintLoaderError(' '.join([
                    "Ambiguous default interface for",
                    f"{self.name}: {claims}"
                ]))

        # Prioritize claims to default interface
        default = (
            select_claim(default_claims['hosts'])
            or select_claim(default_claims['net'])
        )
        if not default:
            log.warning(
                f"Unknown default interface for {self.name}: \n"
                f"Default claims: {default_claims}"
            )
            raise BlueprintLoaderError(
                f"Unknown default interface for {self.name}"
            )

        for iface in self.interfaces.values():
            iface.is_default_iface = True if iface == default else False

        log.info(' '.join([
            f"Interfaces on {self.name}:",
            ', '.join([ iface.name for iface in self.interfaces.values() ])
        ]))


    def _add_interface(self, iface_net_name, iface_spec=None):

        log.debug(f"Adding interface: {iface_net_name} - {iface_spec}")
        iface_spec = iface_spec or {}
        iface_spec['name'] = f"{iface_net_name}.{self.name}"
        iface_spec['network'] = (('network', iface_net_name),)
        if iface_spec['network'] not in self.env.networks:
            raise BlueprintLoaderError(f"No network {iface_net_name} available for {self.name}")

        # Determine immediate parent network of interface
        for net_fqn, net in self.env.networks.items():

            # Skip if top level network doesn't match
            if net_fqn[0] != ("network", iface_net_name):
                continue

            # Network name matching the host name means
            # it's an isolated subnet the host goes into
            if net_fqn[-1] == ("network", self.name):  # isolated subnet
                iface_parent_net = net
                break
        else:
            # Parent net is 
            iface_parent_net = self.env.networks[iface_spec['network']]


        #iface_spec['network'] = networks[iface_net_name]
        #self.interfaces[(('iface', iface_net_name),)] = 
        Interface(
            self.env, iface_spec, iface_parent_net, self
        )


    def _get_extra_serial_data(self):

        return {
            'interfaces': {
                str(iface.fqn): iface.serialized
                for iface in self.interfaces.values()
            }, #self._fqn_str_list(self.interfaces),
            'service_instances': [
                str(fqn)
                for fqn in self.service_instances
                #for inst in inst_list
            ]
        }


