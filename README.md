# Systogony Core

*Sing, O Muse, of the ordering of Systems from void -*  
*of Networks hewn from chaos, Subnets apportioned by law,*  
*of Services arrayed in their stations, each bound to its Host,*  
*and the Rules that govern all passage between them,*  
*that no packet cross unbidden, and no Host stand unknown.*

---

Systogony Core ingests a structured blueprint - YAML files describing hosts, networks, services, and other variables - and resolves them into a calculated, fully-connected object graph. It then exposes that graph to downstream automation via a CLI and Python API, feeding structured data to Ansible and Terraform without requiring those tools to hold or re-derive environment topology themselves.

**Alpha Warning**: This is tooling for personal infrastructure, not a general-purpose framework - at least at this point. Interfaces are under foundational development and subject to change without notice.

---

### Design Goals

- Minimize redundant specification - an environment change should be made in exactly one place in the blueprint
- Treat service instances as first-class addressable resources, rather than properties of their host systems
- Control access between systems granularly using network microsegmentation and comprehensive default-deny firewall rules
- Allow resources to be referenced by association (e.g., "all hosts running a given service", "all services on a given network")
- Provide enough flexibility to override parameters at the right level of specificity

---

### How It Works

#### Blueprint

The blueprint is a directory of YAML files, split into four component types:

- **`hosts.yaml`** - physical and virtual machines, with their network interfaces and group memberships
- **`networks.yaml`** - network topology, including hierarchical subnets, CIDR assignments, and isolation schemes
- **`services.yaml`** - services running in the environment, the hosts they run on, their ports, and their ACL relationships
- **`vars.yaml`** *(optional)* - environment-level variables passed through to automation

Each component type can alternatively be split across a same-named subdirectory (e.g., `blueprint/services/` containing multiple `.yaml` files), which are merged at load time.

#### Resource Model

Blueprint definitions are internalized as a graph of typed resource objects:

| Resource Type | Description |
|---|---|
| `Host` | A machine or device in the environment |
| `Network` | A network or subnet, with optional auto-generated child subnets |
| `Interface` | A connection between a Host and a Network, carrying IP assignment and firewall rules |
| `Service` | A service definition, including ports and ACL intent |
| `ServiceInstance` | A connection between a Service and a Host - the runtime presence of a service |
| `Acl` | A calculated network allow rule between sources and destinations on specific ports |

Every resource is assigned a **fully-qualified name (FQN)** composed of its type and name (and lineage for subnets and instances). Resources can be referenced in the blueprint using a **shorthand** notation that resolves to the narrowest contextually relevant match - for example, `home-net.svc.prometheus` resolves to service instances of Prometheus reachable via the `home-net` network.

#### Service Defaults (`services.d/`)

The `services.d/` directory contains YAML files defining default variables for known services (ports, base directories, metrics endpoints, etc.). Services in the blueprint inherit from these defaults by name, and can override individual values. Service defaults can also reference another service as a parent to inherit from, resolved iteratively at startup.

#### ACLs

ACLs are declared in the blueprint on hosts, networks, or services using two keys:

- **`allows`** - declares that the listed resources are allowed to send traffic *to* this resource on its ports
- **`access`** - declares that this resource is allowed to send traffic *to* the listed resources on their ports

At load time, all ACL declarations are resolved through the shorthand query system and internalized as `Acl` objects. These are then attached to the relevant `Interface` objects and surfaced as firewall rules, organized by direction (ingress, egress, forward).

---

### CLI

The CLI is built on [declib](https://github.com/dechandler/declib) and follows a subcommand-oriented argument consumption pattern.

```
systogony [subcommand] [args...]
```

With no arguments, `systogony` defaults to printing the Ansible inventory.

#### `print` / `list` / `ls`

Print computed environment data as JSON.

```
systogony print ansible       # Ansible dynamic inventory
systogony print terraform     # Terraform template data
systogony print introspection [networks|hosts|interfaces|services|service_instances|acls|all]
```

#### `ansible` / `a` / `ans`

Run `ansible-playbook` with systogony as the dynamic inventory source.

```
systogony ansible site.yaml
systogony ansible site.yaml --tags deploy
```

Passes `-K` (become password) by default. Pass `--ask-vault-pass` behavior is controlled by config.

Because `systogony` implements the Ansible dynamic inventory interface (responding to `--list`), it can be passed directly as the inventory source:

```
ansible-playbook -i /path/to/systogony site.yaml
```

#### `terraform` / `tf`

Manage Terraform operations against the configured environment directory.

```
systogony terraform generate   # Render Terraform templates with blueprint data
systogony terraform init
systogony terraform plan
systogony terraform apply
systogony terraform destroy
```

---

### Ansible Integration

`AnsibleApi` produces a dynamic inventory in standard Ansible JSON format. Groups generated include:

- `systems` - all host machines
- `service_instances` - all service instance quasi-hosts
- `login_{hostname}` - a host system and all of its service instances (shares connection variables)
- `svc_{service_name}` - all instances of a given service
- `managed` / `unmanaged` - hosts with or without a supported OS
- Any groups declared in the blueprint under a host's `groups` key

Service instances are surfaced as quasi-hosts named `{hostname}_inst_{service_name}`, with their vars (ports, interfaces, service config) attached as `host_vars`. The parent host's connection variables are shared through the `login_{hostname}` group vars.

---

### Terraform Integration

`TerraformApi` produces a data structure for use in Jinja2-templated `.tf` and `.tfvars` files. The `terraform generate` command renders templates from `terraform/templates/{env_name}/` into the configured output directory, passing in host variables, environment config, and blueprint vars.

Currently, Linode/Akamai is the supported cloud platform (filtered by `platform: linode` in host spec).

---

### Configuration

Configuration is managed through [declib](https://github.com/dechandler/declib)'s config system. Defaults can be overridden via config file.

| Key | Default | Description |
|---|---|---|
| `blueprint_path` | `blueprint` | Path to the blueprint directory |
| `secrets_dir` | `secrets` | Path to secrets directory |
| `tf_env_dir` | `terraform` | Path to Terraform environment output directory |
| `ansible_dir` | `~/src/systogony-automation/ansible` | Path to the Ansible working directory |
| `environments` | `{}` | Named environment override blocks |
| `default_env` | `null` | Name of the environment to apply by default |
| `use_cache` | `false` | Cache computed inventory/template data to disk |
| `force_cache_regen` | `false` | Force cache regeneration even if blueprint is unchanged |
| `ask_become_pass` | `true` | Pass `-K` when invoking ansible-playbook |
| `ask_vault_pass` | `false` | Pass `--ask-vault-pass` when invoking ansible-playbook |

---

### Blueprint Example

The following is a condensed illustration from the `blueprints/demo/` sample.

#### `hosts.yaml`

```yaml
home-server:
  groups: ['service']
  interfaces:
    home-net:
    ts:
      ip: 100.100.100.103

laptop-me:
  groups: ['laptop']
  interfaces:
    home-net:
    ts:
      ip: 100.100.100.105
```

#### `networks.yaml`

```yaml
home-net:
  type: router
  cidr: 192.168.0.0/16
  subnets:
    service:
      type: isolation
      cidr_prefix_offset: 7
      cidr_index: 19
    laptop:
      type: isolation
      cidr_prefix_offset: 7
      cidr_index: 17

ts:
  type: tailscale
  cidr: 100.64.0.0/10
```

Subnet CIDR calculations can be controlled relative to the parent network's CIDR, rather than explicitly. `cidr_prefix_offset` is added to the parent network's prefix length to determine the subnet size, so a parent of 192.168.0.0/16 with an offset of 5 produces /21 subnets. `cidr_index` then selects which of those subnets to assign - index 3 picks the fourth /21 block, which would be 192.168.24.0/21.

Networks of type `isolation` automatically generate one `/30` subnet per member host, placing each host in its own isolated segment. Networks of type `router` define subnets explicitly.

#### `services.yaml`

```yaml
syncthing-server:
  hosts:
    home-server:
  interfaces:
    net.ts:
  ports:
    http: 8384
  allows:
    svc.admin:

syncthing-desktop:
  hosts:
    laptop-me:

syncthing-peer:
  hosts:
    svc.syncthing-server:
    svc.syncthing-desktop:
  ports:
    data: 22000
    data_udp: udp/22000
  allows:
    net.laptops:
    net.services:
```

`svc.syncthing-server` and `svc.syncthing-desktop` as host shorthands resolve to the hosts running those services. `net.laptops` and `net.services` resolve to the networks whose names match those groups, providing a concise way to express segmentation policies.

---

### Installation

Requires Python > 3.8.

```
pip install git+https://github.com/dechandler/systogony-core
```

Dependencies: `pyyaml`, [`declib`](https://github.com/dechandler/declib)

---

### Project Structure

```
systogony/
  __main__.py          Entry point
  config.py            Configuration and service defaults loader
  api/
    api.py             Base API class
    ansible.py         Ansible dynamic inventory generation
    terraform.py       Terraform template data and file generation
    introspection.py   Structured introspection of all resource types
  cli/
    main.py            Top-level CLI router
    print.py           Print subcommand (JSON output)
    ansible.py         Ansible subcommand (ansible-playbook wrapper)
    terraform.py       Terraform subcommands
  environment/
    blueprint.py       Blueprint file loading and resource population
    environment.py     Environment object graph and resource registry
  resource/
    resource.py        Base resource class, shorthand resolution, ACL generation
    host.py            Host resource
    network.py         Network resource (CIDR, subnet generation)
    interface.py       Interface resource (IP assignment, firewall rules)
    service.py         Service resource (port and var inheritance)
    service_instance.py  ServiceInstance resource
    acl.py             Acl resource
services.d/            Service default variable definitions
blueprints/            Blueprint directories (demo included)
```