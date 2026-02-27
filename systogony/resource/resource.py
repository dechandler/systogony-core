
import logging

from functools import cached_property

from ..exceptions import NonMatchingPathSignal, BlueprintLoaderError

log = logging.getLogger("systogony")


class Resource:

    def __init__(self, env, spec):

        self.env = env
        self.log = env.config.log
        self.spec = spec

        self.name = spec['name']


        #self.env.names[self.name].append(self)

        self.fqn = tuple([(self.resource_type, spec['name'])])
        #self.fqn = tuple([*parent.fqn, fqn] if parent else [fqn])

        self.fqn_str = '.'.join([ '.'.join(pair) for pair in self.fqn ])

        # Register 
        self.env.register(self)

        # Shortcut to associated resources by type
        # self.hosts = {self.host.fqn: self.host}
        # self.interfaces = {self.fqn: self}
        # self.networks = {network.fqn: network}
        # self.services = {}  # connected via service_instances
        self.acls = {
            'owned': {},
            'ingress': {},
            'egress': {},
            'forward': {}
        }

        self.spec_var_ignores = [
            'hosts', 'interfaces', 'allows', 'access', 'restrictions', 'name'
        ]
        #self.extra_vars = {}

        self.parent = None
        self.children = {}
        self.network = None
        #self.ports = None
        #self.rules = {'input': [], 'output': [], 'forward': []}


        self.parents = []


    @property
    def serialized(self):

        attrs = {
            'name': self.name,
            'fqn': str(self.fqn),
            'resource_type': self.resource_type
        }

        if self.network:
            attrs['network'] = str(self.network.fqn)
        #attrs['parent'] = str(self.parent.fqn) if self.parent else None

        attrs.update(self._get_extra_serial_data())

        return attrs

    def __gt__(self, other):
        return self.name > other.name
    def __lt__(self, other):
        return self.name < other.name
    def __ge__(self, other):
        return self.name >= other.name
    def __le__(self, other):
        return self.name <= other.name


    def _get_extra_serial_data(self):
        return {}

    # def _fqn_str_list(self, resources_dict):

    #     return [ str(resource.fqn) for resource in resources_dict.values() ]


    # def _fqns_strs(self, targets):

    #     items = []
    #     for target in targets:
    #         target_items = []
    #         for pair in target:
    #             target_items.extend(pair)
    #         items.append('.'.join(target_items))
    #     return items

    @property
    def short_fqn_str(self):

        return '.'.join([ pair[1] for pair in self.fqn ])

    @property
    def addresses(self):
        addrs = {}
        for iface in self.interfaces.values():
            net = iface.network.network
            if net.fqn not in addrs:
                addrs[net.fqn] = []
            for iface_addresses in iface.addresses.values():
                addrs[net.fqn].extend(iface_addresses)
        return addrs

    @cached_property
    def vars(self):

        rvars = {
            k: v for k, v in self.spec.items() if k not in self.spec_var_ignores
        }
        rvars.update(self.extra_vars)
        return rvars

    @cached_property
    def extra_vars(self):
        return {}


    def gen_acls(self):
        """
        Creates Acl objects that associate themselves with related objects


        """
        # Called from SystogonyEnvironment.__init__()

        for acl_spec_type in ['allows', 'access']:
            if self.spec.get(acl_spec_type):
                self._gen_acls_by_spec_type(acl_spec_type)

    def _gen_acls_by_spec_type(self, acl_spec_type):
        """
        acl types: 'allows', 'access'


        """
        # Called from self.gen_acls()

        # Get matches for 
        sources = {}
        destinations = {}
        target_specs = {}
        for shorthand, overrides in self.spec[acl_spec_type].items():
            try:
                matches = self.env.get_shorthand_matches(shorthand)
            except BlueprintLoaderError:
                # Leaving this as ok for now, but should let the error
                #   surface once Listener resource is implemented
                self.log.error(f"Lookup failure on {shorthand} in {self.name}")
                continue

            for match in matches:
                if acl_spec_type == "allows":
                    src, dest = match, self
                elif acl_spec_type == "access":
                    src, dest = self, match
                sources[src.fqn] = src
                destinations[dest.fqn] = dest

                target_specs[match.fqn] = {**(overrides or {})}


        # TODO: generic ports
        acl_spec = {}
        if acl_spec_type == "allows":
            ports = self.ports

        elif acl_spec_type == "access":
            ports = {}
            for target in destinations.values():
                ports.update(target.ports)

        owner_str = self.name
        targets_str = '-'.join([t.name for t in destinations.values()])
        src_str = ','.join([s.name for s in sources.values()])
        dest_str = ','.join([s.name for s in destinations.values()])


        acl_spec.update({
            'name': "_".join([owner_str, acl_spec_type, targets_str]),
            'origin': self,
            'description': " ".join([
                f"{src_str} TO {dest_str} ON",
                ','.join([str(p) for p in ports.values()])
            ]),
            'ports': ports
        })
        self.env.gen_acl(self, acl_spec, sources, destinations)

    def short_fqns_strs(self, targets):

        return [ t.short_fqn_str for t in targets.values() ]



    def is_shorthand_match(self, shorthand):

        # Deep copy shorthand so we can modify it without poisoning
        #   the matching for sibling resources
        shorthand = [*shorthand]

        # Remove matching terms from right side of working shorthand
        if shorthand and shorthand[-1] == self.name:
            shorthand.pop(-1)
        if shorthand and shorthand[-1] in self.shorthand_type_matches:
            shorthand.pop(-1)

        # If shorthand is empty now, this resource matches
        if not shorthand:
            return True

        # Ask each parent to check itself and its parents for
        # matching of remaining shorthand segments
        for parent in self.parents:
            if parent.is_shorthand_match(shorthand):
                return True

            # match = parent.is_shorthand_match(shorthand)
            # if match:
            #     return match

        # If this resource doesn't match, and none of its
        # parents know a match, this search tree is closed
        return False


    def get_descendents(self, types=None):

        if types is None:
            types = [
                'networks', 'hosts', 'interfaces',
                'services', 'service_instances'
            ]
        descendents = []
        for child in self.children.values():
            descendents.append(child)
            descendents.extend(child.get_descendents(types))
        return descendents
